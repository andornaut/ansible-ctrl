# ansible-role-nas

Manages encrypted BTRFS RAID arrays on Ubuntu.

## Usage

```bash
make nas

ansible-playbook --ask-become-pass nas.yml --tags backupnas
```

## Tags

| Tag | Description |
| --- | --- |
| backupnas | Configure backup LUKS devices and install the `backupnas` script |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- `nas-mount.service` is a systemd oneshot that mounts the array on boot if the LUKS key file exists. It runs
  after `local-fs.target` and starts `media-nas.mount`, which pulls in the LUKS unlock via fstab's systemd
  dependencies.

## Setup

The role does not create the LUKS devices, the filesystem, or the fstab and crypttab entries. Do that once, by
hand, before applying it.

1. Create the LUKS-encrypted devices:

   ```bash
   device=/dev/disk/by-id/...
   cryptsetup luksFormat ${device}

   # Add a key file
   keyfile=/path/to/keyfile
   head -c 256 /dev/random > ${keyfile}
   cryptsetup luksAddKey ${device} ${keyfile}

   # Map the encrypted container, repeating for nas1, nas2, and so on
   cryptsetup luksOpen --key-file ${keyfile} ${device} nas0
   ```

2. Create the BTRFS RAID array:

   ```bash
   mkfs.btrfs -m raid1 -d raid1 /dev/mapper/nas0 /dev/mapper/nas1

   mount \
       -t btrfs /dev/mapper/nas0 \
       -o device=/dev/mapper/nas0,device=/dev/mapper/nas1 \
       /media/nas

   btrfs filesystem show /media/nas
   ```

3. Add the mapper devices to `/etc/crypttab`, as `<mapper name> <UUID> <key file> <options>`:

   ```text
   nas0 UUID-0000-1111-2222 /root/luks-key luks,noauto
   nas1 UUID-3333-4444-5555 /root/luks-key luks,noauto
   nasbackup /dev/disk/by-id/ata-XXX-YYY_ZZZZ /root/luks-key luks,noauto
   ```

4. Add the mount points to `/etc/fstab`, as `<device> <mount point> <filesystem> <options>`:

   ```text
   /dev/mapper/nas0 /media/nas btrfs defaults,noauto,device=/dev/mapper/nas0,x-systemd.after=blockdev@dev-mapper-nas0.target,x-systemd.requires=dev-mapper-nas0.device,x-systemd.requires-mounts-for=/dev/mapper/nas0,device=/dev/mapper/nas1,x-systemd.after=blockdev@dev-mapper-nas1.target,x-systemd.requires=dev-mapper-nas1.device,x-systemd.requires-mounts-for=/dev/mapper/nas1,x-systemd.device-timeout=20s 0 0

   /dev/mapper/nasbackup /media/nasbackup btrfs defaults,noauto,x-systemd.after=blockdev@dev-mapper-nasbackup.target,x-systemd.requires=dev-mapper-nasbackup.device,x-systemd.requires-mounts-for=/dev/mapper/nasbackup,x-systemd.device-timeout=20s 0 0
   ```

## Operations

```bash
# Check the auto-mount service
systemctl status nas-mount.service

# Mount and unmount
systemctl start media-nas.mount
systemctl stop media-nas.mount
systemctl stop systemd-cryptsetup@nas*.service

# Mount and unmount without systemd
cryptdisks_start nas0 && cryptdisks_start nas1 && mount /media/nas
umount /media/nas && cryptdisks_stop nas0 && cryptdisks_stop nas1

# Mount a degraded array, for recovery or maintenance when a device is missing
mount -o degraded /dev/mapper/nas0 /media/nas

# Back up to the backup array
mount /media/nasbackup
backupnas
```

## References

- [Btrfs Multi Device Dmcrypt](http://marc.merlins.org/perso/btrfs/post_2014-04-27_Btrfs-Multi-Device-Dmcrypt.html)
- [Cryptsetup Documentation](https://gitlab.com/cryptsetup/cryptsetup)
- [BTRFS Wiki - Multiple Devices](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices)
