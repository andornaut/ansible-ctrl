# ansible-role-nas

Mount, unmount, and backup encrypted BTRFS raid arrays.

## Creating a BTRFS raid1 array of LUKS-encrypted devices

- [Btrfs Multi Device Dmcrypt](http://marc.merlins.org/perso/btrfs/post_2014-04-27_Btrfs-Multi-Device-Dmcrypt.html)
- [Cryptsetup](https://gitlab.com/cryptsetup/cryptsetup)
- [Using Btrfs with Multiple Devices](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices)

```bash
# Create LUKS devices
device=/dev/disk/by-id/...
cryptsetup luksFormat ${device}

# Add a key-file (which can be used instead of the passphrase created above)
keyfile=/path/to/keyfile
head -c 256 /dev/random > ${keyfile}
cryptsetup luksAddKey ${device} ${keyfile}

# Map the container to /dev/mapper/nas0
cryptsetup luksOpen --key-file ${keyfile} ${device} nas0

# Repeat for second device: /dev/mapper/nas1

# Create BTRFS raid1 array
mkfs.btrfs -m raid1 -d raid1 /dev/mapper/nas0 /dev/mapper/nas1

# Mount the array
mount \
    -t btrfs /dev/mapper/nas0 \
    -o device=/dev/mapper/nas0,device=/dev/mapper/nas1 \
    /media/nas

btrfs filesystem show /media/nas
```

## Example /etc/crypttab and /etc/fstab

/etc/crypttab

```
nas0 UUID-0000-1111-2222 /root/luks-key luks,noauto
nas1 UUID-3333-4444-5555 /root/luks-key luks,noauto

```

/etc/fstab

```
/dev/mapper/nas0 /media/nas btrfs noauto,device=/dev/mapper/nas0,device=/dev/mapper/nas1 0 0
```

## Usage

#### Mounting

```
systemctl start media-nas.mount
```

Alternative:

```
cryptdisks_start nas0
cryptdisks_start nas1
mount /media/nas
```

#### Mounting degraded

Mounting [a degraded array](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices#Replacing_failed_devices):

```bash
mount -o degraded /dev/mapper/nas0 /media/nas1
```

#### Unmounting

```
systemctl stop media-nas.mount
systemctl stop systemd-cryptsetup@nas*.service
```

Alternative:

```
umount /media/nas
cryptdisks_stop nas0
cryptdisks_stop nas1
```
