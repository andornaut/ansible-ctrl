# ansible-role-nas

Installs the mount service, backup script and monthly scrub for encrypted BTRFS RAID arrays on Ubuntu.

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

## Installed files

| Path                                    | Purpose                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------- |
| `/etc/crypttab`, `/etc/fstab`           | Entries for the RAID and backup devices                                   |
| `/etc/systemd/system/nas-mount.service` | Unlocks the RAID devices and mounts `nas_raid_mount_directory`            |
| `/usr/local/bin/backupnas`              | Copies `nas_backup_source_directory` to a backup device (`backupnas` tag) |
| `/usr/local/sbin/nas-scrub`             | Scrubs the array (`scrub` tag)                                            |
| `/etc/cron.d/ansible-role-nas`          | Monthly `nas-scrub` entry                                                 |

## Notes

| Constraint                        | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nas-mount.service`               | A systemd oneshot that unlocks each RAID device with `cryptdisks_start` and then starts the mount unit of `nas_raid_mount_directory` (`media-nas.mount` by default). With `nas_key_file_mount_unit` set it runs after and binds to that unit; otherwise it runs after `local-fs.target` only if the LUKS key file exists                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `backupnas`                       | Refuses an empty source, since the mirror deletes, and refuses to run while rsnapshot's lockfile `/var/run/rsnapshot.pid` exists. Unlocks and mounts the first backup device it finds, mirrors `nas_backup_source_directory` excluding the top-level `rsnapshot/` snapshot root (deleting files no longer in the source, never the `rsnapshot.<date>/` copies), copies the newest `weekly` snapshot (the lowest-numbered `weekly.N` under that `rsnapshot/`) to `rsnapshot.<date>/` with unchanged files hard-linked to the newest previous copy, deletes all but the newest `nas_backup_rsnapshot_retention` of those copies, then unmounts and locks the device. It exits non-zero if the device is left mounted or unlocked, and on any failed exit prints the `umount` and `cryptdisks_stop` commands for a device still unlocked, without running them. `--help` lists its flags |
| `nas-scrub`                       | Runs `btrfs scrub` on `nas_raid_mount_directory` once a month (`nas_scrub_day`, `nas_scrub_hour`, `nas_scrub_minute`), on a btrfs array only. It prints nothing on success, so cron mails only a failure: the array not mounted, uncorrectable errors, or nonzero device error counters                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Error counters are cumulative     | On raid1 a scrub repairs a corrupt block from the other copy, so a corrected error still shows in the counters. They keep reporting until reset with `btrfs device stats -z`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| The backup device is not scrubbed | `backupnas` reads that device only when a backup runs, so scrub it then, before the next backup relies on the copies it keeps. With a single data copy, a scrub detects corruption but cannot repair it. See [Operations](#operations)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

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
