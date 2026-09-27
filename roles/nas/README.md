# ansible-role-nas

Installs the mount service and backup script for encrypted BTRFS RAID arrays on Ubuntu. The base role's `btrfs` tag scrubs,
balances and snapshots the array.

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

## Installed files

| Path                                    | Purpose                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------- |
| `/etc/crypttab`, `/etc/fstab`           | Entries for the RAID and backup devices                                   |
| `/etc/systemd/system/nas-mount.service` | Unlocks the RAID devices and mounts `nas_raid_mount_directory`            |
| `/usr/local/bin/backupnas`              | Copies `nas_backup_source_directory` to a backup device (`backupnas` tag) |

## Notes

| Constraint                        | Detail                                                                                                                                                                                                                                                                                |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nas-mount.service`               | Waits for `nas_key_file_mount_unit` when set; otherwise it starts only if the LUKS key file exists                                                                                                                                                                                    |
| `backupnas`                       | Mirrors the source to the first backup device it finds (deleting what the source no longer has), keeps `nas_backup_rsnapshot_retention` dated copies of the newest `weekly` snapshot, then locks the device. Refuses an empty source or a running rsnapshot. `--help` lists its flags |
| The backup device is not scrubbed | Exclude it with `base_btrfs_excluded_mountpoints` and scrub it during a backup, before the next one relies on its copies; with a single data copy a scrub detects corruption but cannot repair it. See [Operations](#operations)                                                      |

## Setup

The role does not create the LUKS devices or the filesystem: do that once, by hand, before applying it. The
crypttab and fstab entries are written by the role.

1. Create the LUKS-encrypted devices:

   ```bash
   device=/dev/disk/by-id/...
   cryptsetup luksFormat ${device}

   # Add a key file, at nas_key_file's default: .nas-luks-key in nas_user's home
   keyfile="$(getent passwd <nas_user> | cut -d: -f6)/.nas-luks-key"
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
systemctl stop 'systemd-cryptsetup@nas[0-9]*.service'

# Mount and unmount without systemd
cryptdisks_start nas0 && cryptdisks_start nas1 && mount /media/nas
umount /media/nas && cryptdisks_stop nas0 && cryptdisks_stop nas1

# Mount a degraded array, for recovery or maintenance when a device is missing
mount -o degraded /dev/mapper/nas0 /media/nas

# Back up to a backup device
backupnas

# Back up, then scrub the backup device before locking it
backupnas --no-unmount
btrfs scrub start -Bd /media/nasbackup
btrfs device stats --check /media/nasbackup
backupnas --unmount-only /dev/mapper/nasbackup
```
