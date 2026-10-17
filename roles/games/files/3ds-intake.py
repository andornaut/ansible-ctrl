#!/usr/bin/env python3
"""Check a Nintendo 3DS image against No-Intro, and decrypt one into the library's .3ds form.

The azahar core loads only decrypted images and does not load a .cia, so every title is
stored as a decrypted .3ds (CCI):

    3ds-intake.py verify  IMAGE [--dat PATH_OR_URL ...]
    3ds-intake.py decrypt SOURCE DEST [--keys PATH] [--seeddb PATH]

verify hashes IMAGE as it is and looks it up in the libretro No-Intro DATs, the card set and
the eShop set unless --dat names others. Run it on the encrypted source: both DATs hash
encrypted, untrimmed images, so a decrypted or trimmed one never matches. A .cia has no DAT
entry, the eShop set listing its titles as .3ds.

decrypt writes DEST, a CCI with every NCCH partition decrypted, from a card image or a CIA.
A card image keeps its partitions where they are, less the padding after the last one. A
CIA's contents become the partitions of the same index (0 the game, 1 the manual, 2 the
download play child). Each partition's ExHeader, ExeFS and RomFS hashes are checked before
DEST appears, so a wrong key fails the run rather than producing an image the core rejects.
DEST must not exist.

Keys come from a Citra-format aes_keys.txt (NAME=hex, one per line), read only when the
source is encrypted: generator, slot0x2CKeyX and the secondary slot the NCCH names
(slot0x25KeyX, slot0x18KeyX or slot0x1BKeyX), plus slot0x3DKeyX and the commonN its ticket
names for an encrypted CIA. A title whose NCCH uses a seed also needs seeddb.bin. Both
default to ~/.3ds/. No key value is printed, an error naming only the key that is missing.
"""

import argparse
import hashlib
import re
import struct
import sys
import urllib.request
import zlib
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DAT_BASE = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/"
DAT_URLS = [DAT_BASE + "Nintendo%20-%20Nintendo%203DS.dat", DAT_BASE + "Nintendo%20-%20Nintendo%203DS%20(Digital).dat"]
DEFAULT_KEYS = Path.home() / ".3ds" / "aes_keys.txt"
DEFAULT_SEEDDB = Path.home() / ".3ds" / "seeddb.bin"

MEDIA_UNIT = 0x200
# A multiple of the AES block, so a CBC decryptor returns every byte it is given.
CHUNK = 4 * 1024 * 1024
# Where a card image's first partition sits, the NCSD and card info headers before it.
CCI_FIRST_PARTITION = 0x4000

# NCCH flags[3] -> the keyslot its secondary key is derived in.
SECONDARY_SLOTS = {0x00: 0x2C, 0x01: 0x25, 0x0A: 0x18, 0x0B: 0x1B}
# NCCH flags[7] bits.
FIXED_KEY, NO_CRYPTO, SEEDED = 0x01, 0x04, 0x20
# The ExeFS files the primary key covers, with the ExeFS header. The rest use the secondary.
PRIMARY_EXEFS_FILES = {b"icon", b"banner"}
# The ExHeader's hashed part, and the part encrypted with it: the access descriptor follows.
EXHEADER_HASHED, EXHEADER_ENCRYPTED = 0x400, 0x800
# The section byte of an NCCH counter.
EXHEADER, EXEFS, ROMFS = 1, 2, 3
# Signature type -> bytes between the type field and the signed body, padding included.
SIGNATURE_SKIP = {
    0x10000: 0x200 + 0x3C,
    0x10001: 0x100 + 0x3C,
    0x10002: 0x3C + 0x40,
    0x10003: 0x200 + 0x3C,
    0x10004: 0x100 + 0x3C,
    0x10005: 0x3C + 0x40,
}
# A TMD body's header and its 64 content info records, ahead of the content chunk records.
TMD_CHUNKS = 0xC4 + 64 * 0x24

DAT_ROM = re.compile(
    r'rom \( name "(?P<name>[^"]*)" size (?P<size>\d+) crc (?P<crc>[0-9A-Fa-f]{8})'
    r"(?: md5 [0-9A-Fa-f]{32})?(?: sha1 (?P<sha1>[0-9A-Fa-f]{40}))?"
)


class IntakeError(Exception):
    pass


def align(value, boundary):
    return -(-value // boundary) * boundary


def normal_key(key_x, key_y, generator):
    """The hardware key scrambler: ROL((ROL(X, 2) ^ Y) + C, 87) over 128 bits."""
    mask = (1 << 128) - 1

    def rol(value, bits):
        return ((value << bits) | (value >> (128 - bits))) & mask

    x, y, c = (int.from_bytes(key, "big") for key in (key_x, key_y, generator))
    return rol(((rol(x, 2) ^ y) + c) & mask, 87).to_bytes(16, "big")


def ctr(key, counter):
    return Cipher(algorithms.AES(key), modes.CTR((counter % (1 << 128)).to_bytes(16, "big"))).decryptor()


def cbc(key, iv):
    return Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()


def parse_keys(text):
    """NAME=hex lines, names lowercased. A value that is not 16 bytes is not a key and is skipped."""
    values = {}
    for line in text.splitlines():
        name, sep, value = line.split("#", 1)[0].partition("=")
        if not sep:
            continue
        try:
            key = bytes.fromhex(value.strip())
        except ValueError:
            raise IntakeError(f"{name.strip()} is not hex") from None
        if len(key) == 16:
            values[name.strip().lower()] = key
    return values


class Keys:
    """aes_keys.txt, read on first use, so a source already in the clear needs no file."""

    def __init__(self, path):
        self.path = Path(path)
        self._values = None

    def value(self, name):
        if self._values is None:
            if not self.path.is_file():
                raise IntakeError(f"{self.path}: not found, and the source is encrypted")
            try:
                self._values = parse_keys(self.path.read_text(encoding="ascii"))
            except IntakeError as error:
                raise IntakeError(f"{self.path}: {error}") from None
        try:
            return self._values[name.lower()]
        except KeyError:
            raise IntakeError(f"{self.path}: no {name}") from None

    def normal(self, slot, key_y):
        return normal_key(self.value(f"slot0x{slot:02X}KeyX"), key_y, self.value("generator"))


class Seeds:
    """seeddb.bin: a u32 count, 12 bytes of padding, then 0x20-byte (title id, seed) entries."""

    def __init__(self, path):
        self.path = Path(path)
        self._seeds = None

    def seed(self, title_id):
        if self._seeds is None:
            if not self.path.is_file():
                raise IntakeError(f"{self.path}: not found, and title {title_id:016x} uses a seed")
            data = self.path.read_bytes()
            (count,) = struct.unpack_from("<I", data)
            self._seeds = {}
            for entry in range(count):
                tid, seed = struct.unpack_from("<Q16s", data, 0x10 + entry * 0x20)
                self._seeds[tid] = seed
        try:
            return self._seeds[title_id]
        except KeyError:
            raise IntakeError(f"{self.path}: no seed for title {title_id:016x}") from None


def crypt_range(handle, start, length, cipher):
    """Run length bytes at start through cipher, in place."""
    position, end = start, start + length
    while position < end:
        handle.seek(position)
        block = handle.read(min(CHUNK, end - position))
        if not block:
            raise IntakeError(f"truncated at 0x{position:x}")
        out = cipher.update(block)
        if len(out) != len(block):
            raise IntakeError(f"a section at 0x{start:x} is not a whole number of AES blocks")
        handle.seek(position)
        handle.write(out)
        position += len(block)


def copy_range(src, dst, start, length, cipher=None):
    """Copy length bytes from src at start to dst's current position, through cipher if given."""
    src.seek(start)
    remaining = length
    while remaining:
        block = src.read(min(CHUNK, remaining))
        if not block:
            raise IntakeError(f"truncated at 0x{start + length - remaining:x}")
        out = cipher.update(block) if cipher else block
        if len(out) != len(block):
            raise IntakeError(f"content at 0x{start:x} is not a whole number of AES blocks")
        dst.write(out)
        remaining -= len(block)


def ncch_keys(keys, seeds, header):
    """The primary and secondary normal keys of an encrypted NCCH."""
    key_y = bytes(header[:0x10])
    program_id = bytes(header[0x118:0x120])
    title_id = int.from_bytes(program_id, "little")
    flags = header[0x188:0x190]
    if flags[7] & FIXED_KEY:
        # Zero for an application. A system title's fixed key is in no aes_keys.txt.
        if (title_id >> 32) & 0x10:
            raise IntakeError(f"title {title_id:016x} is a fixed-key system title")
        return bytes(16), bytes(16)
    secondary_y = key_y
    if flags[7] & SEEDED:
        seed = seeds.seed(title_id)
        if hashlib.sha256(seed + program_id).digest()[:4] != bytes(header[0x114:0x118]):
            raise IntakeError(f"{seeds.path}: the seed for title {title_id:016x} fails the NCCH's seed check")
        secondary_y = hashlib.sha256(key_y + seed).digest()[:0x10]
    slot = SECONDARY_SLOTS.get(flags[3])
    if slot is None:
        raise IntakeError(f"unknown NCCH crypto method 0x{flags[3]:02x}")
    return keys.normal(0x2C, key_y), keys.normal(slot, secondary_y)


def ncch_counter(header, section, section_offset):
    """The CTR counter at the start of a section: by section id, or by byte offset in version 1."""
    partition_id = bytes(header[0x108:0x110])
    if struct.unpack_from("<H", header, 0x112)[0] == 1:
        return int.from_bytes(partition_id + bytes(4) + section_offset.to_bytes(4, "big"), "big")
    return int.from_bytes(partition_id[::-1] + bytes([section]) + bytes(7), "big")


def decrypt_exefs(handle, start, size, primary, secondary, counter):
    handle.seek(start)
    data = handle.read(size)
    out = bytearray(ctr(primary, counter).update(data))
    for entry in range(10):
        name, offset, length = struct.unpack_from("<8sII", out, entry * 0x10)
        name = name.rstrip(b"\0")
        if not name or not length or name in PRIMARY_EXEFS_FILES:
            continue
        begin = 0x200 + offset
        end = min(begin + align(length, MEDIA_UNIT), size)
        out[begin:end] = ctr(secondary, counter + begin // 0x10).update(data[begin:end])
    handle.seek(start)
    handle.write(out)


def sha256_range(handle, start, length):
    digest = hashlib.sha256()
    handle.seek(start)
    remaining = length
    while remaining:
        block = handle.read(min(CHUNK, remaining))
        if not block:
            raise IntakeError(f"truncated at 0x{start + length - remaining:x}")
        digest.update(block)
        remaining -= len(block)
    return digest.digest()


def sections(header):
    """(offset, size, hash region size) in bytes for the ExeFS and the RomFS."""
    exefs = struct.unpack_from("<III", header, 0x1A0)
    romfs = struct.unpack_from("<III", header, 0x1B0)
    return [value * MEDIA_UNIT for value in exefs], [value * MEDIA_UNIT for value in romfs]


def check_ncch(handle, offset, header):
    """Compare each section with the hash its header records."""
    exheader_size = struct.unpack_from("<I", header, 0x180)[0]
    if exheader_size and sha256_range(handle, offset + 0x200, EXHEADER_HASHED) != header[0x160:0x180]:
        raise IntakeError(f"ExHeader hash mismatch in the NCCH at 0x{offset:x}: a wrong key or a damaged source")
    (exefs_offset, exefs_size, exefs_hashed), (romfs_offset, romfs_size, romfs_hashed) = sections(header)
    if exefs_size:
        start = offset + exefs_offset
        if sha256_range(handle, start, exefs_hashed) != header[0x1C0:0x1E0]:
            raise IntakeError(f"ExeFS hash mismatch in the NCCH at 0x{offset:x}: a wrong key or a damaged source")
        handle.seek(start)
        exefs_header = handle.read(0x200)
        for entry in range(10):
            name, file_offset, length = struct.unpack_from("<8sII", exefs_header, entry * 0x10)
            if not name.rstrip(b"\0"):
                continue
            # Hashes are stored last file first.
            recorded = exefs_header[0x200 - 0x20 * (entry + 1) : 0x200 - 0x20 * entry]
            if sha256_range(handle, start + 0x200 + file_offset, length) != recorded:
                label = name.rstrip(b"\0").decode("ascii", "replace")
                raise IntakeError(f"ExeFS {label} hash mismatch in the NCCH at 0x{offset:x}: a wrong secondary key")
    if romfs_size and sha256_range(handle, offset + romfs_offset, romfs_hashed) != header[0x1E0:0x200]:
        raise IntakeError(f"RomFS hash mismatch in the NCCH at 0x{offset:x}: a wrong secondary key")


def decrypt_ncch(keys, seeds, handle, offset):
    """Decrypt the NCCH at offset in place, mark it unencrypted, and check its hashes."""
    handle.seek(offset)
    header = bytearray(handle.read(0x200))
    if header[0x100:0x104] != b"NCCH":
        raise IntakeError(f"no NCCH at 0x{offset:x}")
    if not header[0x18F] & NO_CRYPTO:
        primary, secondary = ncch_keys(keys, seeds, header)
        if struct.unpack_from("<I", header, 0x180)[0]:
            cipher = ctr(primary, ncch_counter(header, EXHEADER, 0x200))
            crypt_range(handle, offset + 0x200, EXHEADER_ENCRYPTED, cipher)
        (exefs_offset, exefs_size, _), (romfs_offset, romfs_size, _) = sections(header)
        if exefs_size:
            counter = ncch_counter(header, EXEFS, exefs_offset)
            decrypt_exefs(handle, offset + exefs_offset, exefs_size, primary, secondary, counter)
        if romfs_size:
            cipher = ctr(secondary, ncch_counter(header, ROMFS, romfs_offset))
            crypt_range(handle, offset + romfs_offset, romfs_size, cipher)
        # The crypto method is cleared and NoCrypto set: azahar refuses an NCCH without it.
        header[0x18B] = 0
        header[0x18F] = (header[0x18F] & ~(FIXED_KEY | SEEDED)) | NO_CRYPTO
        handle.seek(offset)
        handle.write(header)
    check_ncch(handle, offset, header)


def partition_table(ncsd):
    return [struct.unpack_from("<II", ncsd, 0x120 + index * 8) for index in range(8)]


def decrypt_cci(keys, seeds, src, dst):
    ncsd = bytearray(src.read(0x200))
    table = partition_table(ncsd)
    end = max(offset + size for offset, size in table)
    copy_range(src, dst, 0, end * MEDIA_UNIT)
    # The padding after the last partition is dropped, so the recorded size follows.
    struct.pack_into("<I", ncsd, 0x104, end)
    dst.seek(0)
    dst.write(ncsd)
    for offset, size in table:
        if size:
            decrypt_ncch(keys, seeds, dst, offset * MEDIA_UNIT)


def signed_body(src, offset, length):
    """A ticket's or TMD's body, after its signature."""
    src.seek(offset)
    blob = src.read(length)
    (signature_type,) = struct.unpack_from(">I", blob)
    if signature_type not in SIGNATURE_SKIP:
        raise IntakeError(f"unknown signature type 0x{signature_type:x} at 0x{offset:x}")
    return blob[4 + SIGNATURE_SKIP[signature_type] :]


def title_key(keys, ticket):
    """The ticket's title key, decrypted with the common key it names."""
    index = ticket[0xB1]
    key = keys.normal(0x3D, keys.value(f"common{index}"))
    return cbc(key, ticket[0x9C:0xA4] + bytes(8)).update(ticket[0x7F:0x8F])


def decrypt_cia(keys, seeds, src, dst):
    head = src.read(0x2020)
    header_size, _, _, cert_size, ticket_size, tmd_size = struct.unpack_from("<IHHIII", head)
    bitmap = head[0x20:0x2020]
    ticket_offset = align(header_size, 64) + align(cert_size, 64)
    tmd_offset = ticket_offset + align(ticket_size, 64)
    content_offset = tmd_offset + align(tmd_size, 64)
    ticket = signed_body(src, ticket_offset, ticket_size)
    tmd = signed_body(src, tmd_offset, tmd_size)
    (count,) = struct.unpack_from(">H", tmd, 0x9E)

    # Present contents in record order, which is the order they are stored in.
    contents, position = [], content_offset
    for record in range(count):
        _, index, content_type, size = struct.unpack_from(">IHHQ", tmd, TMD_CHUNKS + record * 0x30)
        if bitmap[index // 8] & (0x80 >> (index % 8)):
            contents.append((index, content_type, size, position))
            position += align(size, 64)
    if not any(index == 0 for index, *_ in contents):
        raise IntakeError("the CIA holds no content 0, so no game: an update or DLC package")
    if any(index >= 8 for index, *_ in contents):
        raise IntakeError("the CIA holds a content index past 7, which a CCI has no partition for")

    key = title_key(keys, ticket) if any(content_type & 1 for _, content_type, _, _ in contents) else None
    ncsd = bytearray(CCI_FIRST_PARTITION)
    out = CCI_FIRST_PARTITION
    placed = []
    for index, content_type, size, start in contents:
        dst.seek(out)
        cipher = cbc(key, index.to_bytes(2, "big") + bytes(14)) if content_type & 1 else None
        copy_range(src, dst, start, size, cipher)
        dst.seek(out)
        ncch = dst.read(0x200)
        struct.pack_into("<II", ncsd, 0x120 + index * 8, out // MEDIA_UNIT, align(size, MEDIA_UNIT) // MEDIA_UNIT)
        ncsd[0x190 + index * 8 : 0x198 + index * 8] = ncch[0x108:0x110]
        if index == 0:
            ncsd[0x108:0x110] = ncch[0x118:0x120]
        placed.append(out)
        out = align(out + size, MEDIA_UNIT)
    dst.truncate(out)

    ncsd[0x100:0x104] = b"NCSD"
    struct.pack_into("<I", ncsd, 0x104, out // MEDIA_UNIT)
    # Partition flags: platform CTR, media type CARD1, 0x200-byte media units.
    ncsd[0x18C], ncsd[0x18D], ncsd[0x18E] = 1, 1, 0
    # Card info header: no writable region, CARD1 keeping saves on a separate chip.
    struct.pack_into("<I", ncsd, 0x200, 0xFFFFFFFF)
    dst.seek(0)
    dst.write(ncsd)
    for offset in placed:
        decrypt_ncch(keys, seeds, dst, offset)


def decrypt(keys, seeds, source, dest):
    if dest.exists():
        raise IntakeError(f"{dest}: already exists")
    with source.open("rb") as src:
        head = src.read(0x200)
        if head[0x100:0x104] == b"NCSD":
            convert = decrypt_cci
        elif len(head) >= 4 and struct.unpack_from("<I", head)[0] == 0x2020:
            convert = decrypt_cia
        else:
            raise IntakeError(f"{source}: neither a CCI nor a CIA")
        partial = dest.with_name(dest.name + ".part")
        try:
            with partial.open("w+b") as dst:
                src.seek(0)
                convert(keys, seeds, src, dst)
            partial.rename(dest)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    print(f"wrote {dest}")


def read_dat(source):
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310
            return response.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


def dat_entries(text):
    """(name, size, crc, sha1) per rom line, hex uppercased, sha1 None where the entry has none."""
    for match in DAT_ROM.finditer(text):
        sha1 = match["sha1"]
        yield match["name"], int(match["size"]), match["crc"].upper(), sha1.upper() if sha1 else None


def hash_file(path):
    crc, sha1, size = 0, hashlib.sha1(), 0  # noqa: S324 - No-Intro's hash, not a security control
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            crc = zlib.crc32(block, crc)
            sha1.update(block)
            size += len(block)
    return size, f"{crc:08X}", sha1.hexdigest().upper()


def verify(image, dats):
    size, crc, sha1 = hash_file(image)
    for source in dats:
        for name, entry_size, entry_crc, entry_sha1 in dat_entries(read_dat(source)):
            if (entry_sha1 or sha1) == sha1 and entry_crc == crc and entry_size == size:
                print(f"match: {name}")
                return 0
    print(f"no match: size {size} crc {crc} sha1 {sha1}")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify", help="look an image up in the No-Intro DATs")
    check.add_argument("image", type=Path)
    check.add_argument("--dat", action="append", help="a DAT path or https URL, repeatable")
    convert = commands.add_parser("decrypt", help="write a decrypted .3ds from a card image or a CIA")
    convert.add_argument("source", type=Path)
    convert.add_argument("dest", type=Path)
    convert.add_argument("--keys", type=Path, default=DEFAULT_KEYS)
    convert.add_argument("--seeddb", type=Path, default=DEFAULT_SEEDDB)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            return verify(args.image, args.dat or DAT_URLS)
        decrypt(Keys(args.keys), Seeds(args.seeddb), args.source, args.dest)
    except IntakeError as error:
        print(f"3ds-intake: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
