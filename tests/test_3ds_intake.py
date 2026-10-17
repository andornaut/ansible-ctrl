import contextlib
import hashlib
import importlib.util
import io
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/3ds-intake.py"


def load(path):
    """Import a script whose file name is not a module name, writing no bytecode beside it."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


intake = load(SCRIPT)

MU = 0x200
TITLE_ID = 0x0004000000ABCD00
# Random stand-ins for console keys: the tests check the layout and which key covers which
# section, not the real values, which this repository never holds.
KEYS = {name: os.urandom(16) for name in ("generator", "slot0x2CKeyX", "slot0x25KeyX", "slot0x3DKeyX", "common0")}
SEED = os.urandom(16)


def keystream_xor(key, counter, data):
    return intake.ctr(key, counter).update(data)


def build_ncch(*, encrypted=True, seeded=False, secondary_x="slot0x25KeyX", method=0x01):
    """An NCCH with an ExHeader, an ExeFS holding .code and icon, and a RomFS.

    Returns (image as stored, the image decrypt should produce).
    """
    exheader = os.urandom(intake.EXHEADER_ENCRYPTED)
    code, icon = os.urandom(0x300), os.urandom(0x100)
    exefs = bytearray(0x800)
    struct.pack_into("<8sII", exefs, 0x00, b".code", 0x000, len(code))
    struct.pack_into("<8sII", exefs, 0x10, b"icon", 0x400, len(icon))
    exefs[0x1E0:0x200] = hashlib.sha256(code).digest()
    exefs[0x1C0:0x1E0] = hashlib.sha256(icon).digest()
    exefs[0x200 : 0x200 + len(code)] = code
    exefs[0x600 : 0x600 + len(icon)] = icon
    romfs = os.urandom(0x1000)

    exefs_offset = 0x200 + len(exheader)
    romfs_offset = exefs_offset + len(exefs)
    header = bytearray(0x200)
    header[:0x100] = os.urandom(0x100)
    header[0x100:0x104] = b"NCCH"
    struct.pack_into("<I", header, 0x104, (romfs_offset + len(romfs)) // MU)
    header[0x108:0x110] = TITLE_ID.to_bytes(8, "little")
    struct.pack_into("<H", header, 0x112, 2)
    header[0x118:0x120] = TITLE_ID.to_bytes(8, "little")
    header[0x160:0x180] = hashlib.sha256(exheader[: intake.EXHEADER_HASHED]).digest()
    struct.pack_into("<I", header, 0x180, intake.EXHEADER_HASHED)
    struct.pack_into("<III", header, 0x1A0, exefs_offset // MU, len(exefs) // MU, 1)
    struct.pack_into("<III", header, 0x1B0, romfs_offset // MU, len(romfs) // MU, 1)
    header[0x1C0:0x1E0] = hashlib.sha256(exefs[:MU]).digest()
    header[0x1E0:0x200] = hashlib.sha256(romfs[:MU]).digest()
    if seeded:
        # Kept through decryption, the SEEDED flag beside it being cleared.
        header[0x114:0x118] = hashlib.sha256(SEED + TITLE_ID.to_bytes(8, "little")).digest()[:4]

    plain = bytearray(header)
    plain[0x18F] = intake.NO_CRYPTO
    plain += exheader + exefs + romfs
    if not encrypted:
        return bytes(plain), bytes(plain)

    header[0x18B] = method
    key_y = bytes(header[:0x10])
    secondary_y = key_y
    if seeded:
        header[0x18F] |= intake.SEEDED
        secondary_y = hashlib.sha256(key_y + SEED).digest()[:0x10]
    primary = intake.normal_key(KEYS["slot0x2CKeyX"], key_y, KEYS["generator"])
    secondary = intake.normal_key(KEYS[secondary_x], secondary_y, KEYS["generator"])
    exefs_counter = intake.ncch_counter(header, intake.EXEFS, exefs_offset)
    sealed_exefs = bytearray(keystream_xor(primary, exefs_counter, bytes(exefs)))
    # .code fills the media units up to icon's offset.
    sealed_exefs[0x200:0x600] = keystream_xor(secondary, exefs_counter + 0x200 // 0x10, bytes(exefs[0x200:0x600]))
    sealed = (
        header
        + keystream_xor(primary, intake.ncch_counter(header, intake.EXHEADER, 0x200), exheader)
        + sealed_exefs
        + keystream_xor(secondary, intake.ncch_counter(header, intake.ROMFS, romfs_offset), romfs)
    )
    return bytes(sealed), bytes(plain)


def build_cci(partitions, padding=0x2000):
    ncsd = bytearray(intake.CCI_FIRST_PARTITION)
    ncsd[0x100:0x104] = b"NCSD"
    body, offset = b"", intake.CCI_FIRST_PARTITION
    for index, ncch in enumerate(partitions):
        struct.pack_into("<II", ncsd, 0x120 + index * 8, offset // MU, len(ncch) // MU)
        body += ncch
        offset += len(ncch)
    struct.pack_into("<I", ncsd, 0x104, (offset + padding) // MU)
    return bytes(ncsd) + body + b"\xff" * padding


def signed(body):
    return struct.pack(">I", 0x10004) + bytes(0x100 + 0x3C) + body


def build_cia(contents):
    """contents: (index, encrypt, ncch). Encrypted ones go through the title key."""
    title_key = os.urandom(16)
    common = intake.normal_key(KEYS["slot0x3DKeyX"], KEYS["common0"], KEYS["generator"])
    tid = TITLE_ID.to_bytes(8, "big")
    sealed_key = Cipher(algorithms.AES(common), modes.CBC(tid + bytes(8))).encryptor().update(title_key)
    ticket_body = bytearray(0x200)
    ticket_body[0x7F:0x8F] = sealed_key
    ticket_body[0x9C:0xA4] = tid
    ticket = signed(bytes(ticket_body))

    tmd_body = bytearray(intake.TMD_CHUNKS + 0x30 * len(contents))
    struct.pack_into(">H", tmd_body, 0x9E, len(contents))
    data, bitmap = b"", bytearray(0x2000)
    for record, (index, encrypt, ncch) in enumerate(contents):
        struct.pack_into(">IHHQ", tmd_body, intake.TMD_CHUNKS + record * 0x30, record, index, int(encrypt), len(ncch))
        bitmap[index // 8] |= 0x80 >> (index % 8)
        stored = ncch
        if encrypt:
            iv = index.to_bytes(2, "big") + bytes(14)
            stored = Cipher(algorithms.AES(title_key), modes.CBC(iv)).encryptor().update(ncch)
        data += stored
    tmd = signed(bytes(tmd_body))

    certs = bytes(0x40)
    header = struct.pack("<IHHIIIIQ", 0x2020, 0, 0, len(certs), len(ticket), len(tmd), 0, len(data)) + bytes(bitmap)

    def padded(blob):
        return blob + bytes(intake.align(len(blob), 64) - len(blob))

    return padded(header) + padded(certs) + padded(ticket) + padded(tmd) + data


class Intake(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.keys = self.root / "aes_keys.txt"
        self.keys.write_text("".join(f"{name}={value.hex().upper()}\n" for name, value in KEYS.items()))
        self.seeddb = self.root / "seeddb.bin"
        self.seeddb.write_bytes(struct.pack("<I12x", 1) + struct.pack("<Q16s8x", TITLE_ID, SEED))

    def decrypt(self, image, keys=None):
        source, dest = self.root / "in.bin", self.root / "out.3ds"
        source.write_bytes(image)
        with contextlib.redirect_stdout(io.StringIO()):
            intake.decrypt(intake.Keys(keys or self.keys), intake.Seeds(self.seeddb), source, dest)
        return dest.read_bytes()

    def test_card_image_partitions_decrypt_in_place_and_padding_is_dropped(self):
        game, game_plain = build_ncch()
        manual, manual_plain = build_ncch(method=0x00, secondary_x="slot0x2CKeyX")
        out = self.decrypt(build_cci([game, manual]))
        first = intake.CCI_FIRST_PARTITION
        self.assertEqual(out[first : first + len(game)], game_plain)
        self.assertEqual(out[first + len(game) :], manual_plain)
        self.assertEqual(struct.unpack_from("<I", out, 0x104)[0], len(out) // MU)

    def test_a_seeded_title_takes_its_seed_from_seeddb(self):
        game, plain = build_ncch(seeded=True)
        out = self.decrypt(build_cci([game]))
        self.assertEqual(out[intake.CCI_FIRST_PARTITION :], plain)

    def test_an_image_in_the_clear_needs_no_key_file(self):
        game, plain = build_ncch(encrypted=False)
        out = self.decrypt(build_cci([game]), keys=self.root / "absent.txt")
        self.assertEqual(out[intake.CCI_FIRST_PARTITION :], plain)

    def test_a_wrong_key_fails_the_hash_check_and_leaves_no_output(self):
        game, _ = build_ncch()
        wrong = dict(KEYS, slot0x25KeyX=os.urandom(16))
        self.keys.write_text("".join(f"{name}={value.hex()}\n" for name, value in wrong.items()))
        with self.assertRaisesRegex(intake.IntakeError, "hash mismatch"):
            self.decrypt(build_cci([game]))
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["aes_keys.txt", "in.bin", "seeddb.bin"])

    def test_a_missing_key_is_named_and_its_value_never_printed(self):
        game, _ = build_ncch()
        self.keys.write_text(f"generator={KEYS['generator'].hex()}\nslot0x2CKeyX={KEYS['slot0x2CKeyX'].hex()}\n")
        with self.assertRaises(intake.IntakeError) as raised:
            self.decrypt(build_cci([game]))
        self.assertIn("no slot0x25KeyX", str(raised.exception))
        for value in KEYS.values():
            self.assertNotIn(value.hex(), str(raised.exception).lower())

    def test_a_cia_becomes_a_cci_with_each_content_at_its_index(self):
        game, game_plain = build_ncch()
        manual, manual_plain = build_ncch(encrypted=False)
        out = self.decrypt(build_cia([(0, True, game), (1, False, manual)]))
        table = intake.partition_table(out)
        self.assertEqual(out[0x100:0x104], b"NCSD")
        self.assertEqual(out[0x108:0x110], TITLE_ID.to_bytes(8, "little"))
        for index, plain in enumerate([game_plain, manual_plain]):
            offset, size = table[index]
            self.assertEqual(out[offset * MU : (offset + size) * MU], plain)

    def test_a_cia_without_content_0_is_refused(self):
        manual, _ = build_ncch(encrypted=False)
        with self.assertRaisesRegex(intake.IntakeError, "no content 0"):
            self.decrypt(build_cia([(1, False, manual)]))

    def test_an_existing_destination_is_never_overwritten(self):
        game, _ = build_ncch(encrypted=False)
        (self.root / "out.3ds").write_bytes(b"keep")
        with self.assertRaisesRegex(intake.IntakeError, "already exists"):
            self.decrypt(build_cci([game]))
        self.assertEqual((self.root / "out.3ds").read_bytes(), b"keep")

    def test_parse_keys_skips_comments_and_values_that_are_not_keys(self):
        values = intake.parse_keys("# dumped\nslot0x2CKeyX=" + "11" * 16 + "\nticketCommonKey=00\n\n")
        self.assertEqual(values, {"slot0x2ckeyx": bytes([0x11]) * 16})


class Verify(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.image = self.root / "game.3ds"
        self.image.write_bytes(b"card image")
        size, crc, sha1 = intake.hash_file(self.image)
        self.entry = f'rom ( name "Game (USA).3ds" size {size} crc {crc} md5 {"0" * 32} sha1 {sha1} )'

    def verify(self, dat):
        path = self.root / "set.dat"
        path.write_text(f'game (\n\tname "Game (USA)"\n\t{dat}\n)\n')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = intake.verify(self.image, [str(path)])
        return status, output.getvalue()

    def test_an_image_whose_hashes_match_names_its_entry(self):
        self.assertEqual(self.verify(self.entry), (0, "match: Game (USA).3ds\n"))

    def test_an_image_matching_no_entry_reports_its_hashes(self):
        _, _, sha1 = intake.hash_file(self.image)
        status, output = self.verify(self.entry.replace(sha1, "F" * 40))
        self.assertEqual(status, 1)
        self.assertTrue(output.startswith("no match: size 10 crc "))


if __name__ == "__main__":
    unittest.main()
