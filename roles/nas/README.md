# ansible-role-nas

Manages encrypted BTRFS RAID arrays on Ubuntu.

## Usage

```bash
make nas
make nas -- --tags backupnas
```

## Tags

| Tag       | Description                                                      |
| --------- | ---------------------------------------------------------------- |
| backupnas | Configure backup LUKS devices and install the `backupnas` script |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- `nas-mount.service` is a systemd oneshot that unlocks each RAID device with `cryptdisks_start` and then starts
  `media-nas.mount`. With `nas_key_file_mount_unit` set it runs after and binds to that unit; otherwise it runs
  after `local-fs.target` only if the LUKS key file exists.

## Setup

The role does not create the LUKS devices or the filesystem: do that once, by hand, before applying it. The
crypttab and fstab entries are written by the role.

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
