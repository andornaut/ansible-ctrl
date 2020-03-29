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
head -c 256 /dev/random > 
cryptsetup luksAddKey ${device} ${keyfile}

# Map the container to /dev/mapper/nas-raid1-a
cryptsetup luksOpen --key-file ${keyfile} ${device} nas-raid1-a

# Create BTRFS raid1 array
mkfs.btrfs -m raid1 -d raid1 /dev/mapper/nas-raid1-a /dev/mapper/nas-raid1-b

# Mount the array
mount \
    -t btrfs /dev/mapper/nas-raid1-a \
    -o device=/dev/mapper/nas-raid1-a,device=/dev/mapper/nas-raid1-b \
    /media/nas

btrfs filesystem show /media/nas
```

Mounting [a degraded array](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices#Replacing_failed_devices):

```bash
mount -o degraded /dev/mapper/nas-raid1-a /media/nas-raid1s-a
```

Umount a luks device

```bash
umount /media/usb
cryptsetup luksClose /dev/mapper/usb
```
