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
| scrub     | Install `nas-scrub` and its monthly cron job                     |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- `nas-mount.service` is a systemd oneshot that unlocks each RAID device with `cryptdisks_start` and then starts
  the mount unit of `nas_raid_mount_directory` (`media-nas.mount` by default). With `nas_key_file_mount_unit` set it
  runs after and binds to that unit; otherwise it runs after `local-fs.target` only if the LUKS key file exists.
- `backupnas` unlocks and mounts the first backup device it finds, copies `nas_backup_source_directory` excluding
  `rsnapshot/`, copies `nas_backup_rsnapshot_source_relative_path` under it to `rsnapshot.<date>/`, deletes all but
  the newest `nas_backup_rsnapshot_retention` of those copies, then unmounts and locks the device. It exits non-zero
  if the device is left mounted or unlocked. `--help` lists its flags.
- `nas-scrub` runs `btrfs scrub` on `nas_raid_mount_directory` once a month (`nas_scrub_day`, `nas_scrub_hour`,
  `nas_scrub_minute`), on a btrfs array only. It prints nothing on success, so cron mails only a failure: the
  array not mounted, uncorrectable errors, or nonzero device error counters. On raid1 a scrub repairs a corrupt
  block from the other copy, so a corrected error still shows in the counters; they are cumulative and keep
  reporting until reset with `btrfs device stats -z`.
- `backupnas` does not scrub the backup device. That device is read only when a backup runs, so scrub it then,
  before the next backup relies on the copies it keeps. With a single data copy, a scrub detects corruption but
  cannot repair it.

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
backupnas

# Back up, then scrub the backup device before locking it
backupnas --no-unmount
btrfs scrub start -Bd /media/nasbackup
btrfs device stats --check /media/nasbackup
backupnas --unmount-only /dev/mapper/nasbackup
```
