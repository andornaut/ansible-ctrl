# ansible-role-nas

Ansible role to manage encrypted BTRFS RAID arrays - mounting, unmounting, and backup operations.

## Overview

This role helps manage:

- LUKS-encrypted BTRFS RAID arrays
- Automated mounting/unmounting
- Backup operations
- Key file management

## Requirements

- Linux system with BTRFS support
- cryptsetup package
- systemd

## Setup Guide

### 1. Creating LUKS-Encrypted Devices

```bash
# Create LUKS container on device
device=/dev/disk/by-id/...
cryptsetup luksFormat ${device}

# Add a key-file (which can be used instead of the passphrase created above)
keyfile=/path/to/keyfile
head -c 256 /dev/random > ${keyfile}
cryptsetup luksAddKey ${device} ${keyfile}

# Map the encrypted container
cryptsetup luksOpen --key-file ${keyfile} ${device} nas0

# Repeat for additional devices (e.g., nas1, nas2, etc.)
```

### 2. Creating BTRFS RAID Array

```bash
# Create RAID1 array from encrypted devices
mkfs.btrfs -m raid1 -d raid1 /dev/mapper/nas0 /dev/mapper/nas1

# Mount the array
mount \
    -t btrfs /dev/mapper/nas0 \
    -o device=/dev/mapper/nas0,device=/dev/mapper/nas1 \
    /media/nas

# Verify array status
btrfs filesystem show /media/nas
```

## Configuration

### crypttab Setup

Add to `/etc/crypttab`:

```text
# Format: <mapper name> <UUID> <key file> <options>
nas0 UUID-0000-1111-2222 /root/luks-key luks,noauto
nas1 UUID-3333-4444-5555 /root/luks-key luks,noauto
```

### fstab Setup

Add to `/etc/fstab`:

```text
# Format: <device> <mount point> <filesystem> <options>
/dev/mapper/nas0 /media/nas btrfs noauto,device=/dev/mapper/nas0,device=/dev/mapper/nas1 0 0
```

## Usage

### Basic Operations

#### Mounting the Array

Using systemd (recommended):

```bash
systemctl start media-nas.mount
```

Manual method:

```bash
cryptdisks_start nas0
cryptdisks_start nas1
mount /media/nas
```

#### Unmounting the Array

Using systemd (recommended):

```bash
systemctl stop media-nas.mount
systemctl stop systemd-cryptsetup@nas*.service
```

Manual method:

```bash
umount /media/nas
cryptdisks_stop nas0
cryptdisks_stop nas1
```

### Backup Operations

```bash
# Mount backup destination
mount /media/nasbackup

# Run backup
backupnas
```

### Advanced Operations

#### Mounting Degraded Array

For recovery or maintenance when a device is missing:

```bash
mount -o degraded /dev/mapper/nas0 /media/nas
```

## Troubleshooting

### Common Issues

1. Mount fails with device busy:
   - Ensure all previous mounts are properly unmounted
   - Check for active processes using the mount point

2. LUKS device won't open:
   - Verify key file permissions
   - Check device UUID matches crypttab entry

## References

- [Btrfs Multi Device Dmcrypt](http://marc.merlins.org/perso/btrfs/post_2014-04-27_Btrfs-Multi-Device-Dmcrypt.html)
- [Cryptsetup Documentation](https://gitlab.com/cryptsetup/cryptsetup)
- [BTRFS Wiki - Multiple Devices](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices)
