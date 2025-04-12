# limelight-3a-mod

Run *any* code on the Limelight 3A.

**DISCLAIMER: This modification is for educational and development purposes only. Modifying a Limelight 3A as described herein may void warranties and potentially violate the rules of FIRST Tech Challenge, or other robotics competitions. Do not use modified Limelights in official competitions without explicit permission from the competition organizers. Vilnius Lyceum Robotics does not endorse or encourage the use of modified hardware in competitive events where such modifications may be against the rules. Users assume all responsibility for any consequences resulting from these modifications.**

# Content
- [Prerequisites](#prerequisites)
  - [How to flash firmware](#how-to-flash-firmware)
- [Gaining root access](#gaining-root-access)
  - [Accessing `/etc/shadow`](#accessing-etcshadow)
  - [Modifying `/etc/shadow`](#modifying-etcshadow)
- [Hardware of the Limelight 3A](#hardware)
  - [Performance, overclocking, and overheating issues](#performance-overclocking--overheating-issues)
- [The Limelight Visionserver](#the-limelight-visionserver)
- [How to get packages & dependencies on the Limelight](#how-to-get-packages--dependencies-on-the-limelight)
  - [System packages](#system-packages)
  - [Python packages](#python-packages)

# Prerequisites
- Limelight 3A with the official firmware image (using 2025.1 here)
- PC running Linux (WSL might be enough)
- `rpiboot` installed
- `dd` installed

## How to flash firmware
Flashing firmware onto the Limelight 3A is pretty straightforward. Hold down the blue button on the front on the device while plugging it in to your PC to but it into the USB bootloader. Then run `$ sudo rpiboot` to open it as a mass storage device, and use `dd` or any other utility to flash the image onto the device:
```sh
$ sudo rpiboot
RPIBOOT: build-date Jan 31 2022 version 0~20220315+git6fa2ec0+nowin-0ubuntu1 
Waiting for BCM2835/6/7/2711...
Loading embedded: bootcode4.bin
Sending bootcode.bin
Successful read 4 bytes 
Waiting for BCM2835/6/7/2711...
Loading embedded: bootcode4.bin
Second stage boot server
Loading embedded: start4.elf
File read: start4.elf
Second stage boot server done
$ lsblk
sda           8:0    1   7.3G  0 disk 
├─sda1        8:1    1    64M  0 part /media/user/4446-55A9
└─sda2        8:2    1   7.2G  0 part /media/user/rootfs
nvme0n1     259:0    0 931.5G  0 disk 
├─nvme0n1p1 259:1    0   100M  0 part /boot/efi
├─nvme0n1p2 259:2    0    16M  0 part 
├─nvme0n1p3 259:3    0 848.5G  0 part 
├─nvme0n1p4 259:4    0   644M  0 part 
└─nvme0n1p5 259:5    0  82.3G  0 part /
$ sudo dd if=/path/to/image.img of=/dev/sda bs=8M status=progress
```

# Gaining root access
SSH is enabled by default on the Limelight 3A's image - the only thing left to do is to change the root password to something you know. You may do that by modifying the entry of the `root` user in `/etc/shadow`.

## Accessing `/etc/shadow`
The methods below will help you gain access to the file. You may choose any one of them, but [Method 2](#method-2-modify-the-image-that-is-currently-on-the-device) is the easiest. [Method 3](#method-3-through-the-python-interface-on-the-limelight) might be the only one that's legal for FTC use.


### Method 1: modify the firmware image
You may modify the firmware image's `/etc/shadow` file on the firmware's .img file. 

1. Find the main partition's sector offset.
```sh
$ fdisk -l /path/to/image.img
```
The output should look something like this:
```sh
$ fdisk -l /path/to/image.img
Disk image.img: 7.28 GiB, 7818182656 bytes, 15269888 sectors
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disklabel type: dos
Disk identifier: 0xf57f7f9e

Device     Boot  Start      End  Sectors  Size Id Type
image.img1    *         1   131072   131072   64M  c W95 FAT32 (LBA)
image.img2         131073 15269887 15138815  7.2G 83 Linux
```
You are looking for the start block number of the main Linux partition on the .img file. In my case, it is `131073`. Keep note of the sector size aswell (should be `512 bytes`).

2. Mount the partition.

To mount the parition, first calculate the partition's offset. It is the start block number multiplied by the sector size in bytes (in my case `131073 * 512 = 67109376`).
```sh
$ sudo mkdir /mnt/tmp
$ sudo mount -o loop,offset=OFFSET /path/to/image.img /mnt/tmp
```
After this, `cd /mnt/tmp` and move to [modifying `/etc/shadow`](#modifying-etcshadow).


### Method 2: modify the image that is currently on the device
1. Plug the Limelight into your computer while holding the blue button on the front of the device to put it into USB bootloader mode, then run `$ sudo rpiboot`.

2. If your distro automatically mounts drives, the `rootfs` partition will be mounted automatically. Else, mount it manually.

### Method 3: through the Python interface on the Limelight
This one is the harder one of the bunch to complete. It relies on the SnapScript Python functionality being ran as `root` on the Limelight internally, theoretically giving you access to `root` without modifying the image using conventional methods, possibly staying legal for FTC (keep in mind that the final decision rests with the judges at your competitions).

Write a Python script to open `/etc/shadow` on runtime and print it out into the console. Then modify it as specified [here](#modifying-etcshadow) and run another script to save the new file contents into the file.  A demo script might be added later on to this doc.

## Modifying `/etc/shadow`
The contents of `/etc/shadow` will look something like this:
```sh
/mnt/tmp$ sudo cat etc/shadow
root:$5$QDFBGOORFV$pN9lgVEFycGo1PWdrn4QTp/UF6ACL8Pa.U92pOF6iJ5:::::::
daemon:*:::::::
bin:*:::::::
sys:*:::::::
sync:*:::::::
mail:*:::::::
www-data:*:::::::
operator:*:::::::
nobody:*:::::::
avahi:*:::::::
dbus:*:::::::
dhcpcd:*:::::::
pi:$5$QDFBGOORFV$pN9lgVEFycGo1PWdrn4QTp/UF6ACL8Pa.U92pOF6iJ5:::::::
systemcore:$5$jr/E6z3n9i80i$TIClwpPY2K2XnQxIdTWIK.0hkdb.Q7ZeEtH9/x/FRP6:::::::
sshd:!*:19746::::::
```
What you are trying to do is to modify the password hashes for the `root` and `pi` users. You may generate password hashes like this:
```sh
$ openssl passwd -5 -salt SOMERANDOMSTRING PASSWORD
$5$SOMERANDOMSTRING$FofHNyv/Y5TMvX.a686QvGplrdWOk8m7bFJxLRi78MC
```
Replace `SOMERANDOMSTRING` with a random string for the salt and `PASSWORD` with the password you want to set. Then replace the hashes in `/etc/shadow` for your new ones.
```sh
root:$5$SOMERANDOMSTRING$FofHNyv/Y5TMvX.a686QvGplrdWOk8m7bFJxLRi78MC:::::::
daemon:*:::::::
bin:*:::::::
sys:*:::::::
sync:*:::::::
mail:*:::::::
www-data:*:::::::
operator:*:::::::
nobody:*:::::::
avahi:*:::::::
dbus:*:::::::
dhcpcd:*:::::::
pi:$5$SOMERANDOMSTRING$FofHNyv/Y5TMvX.a686QvGplrdWOk8m7bFJxLRi78MC:::::::
systemcore:$5$jr/E6z3n9i80i$TIClwpPY2K2XnQxIdTWIK.0hkdb.Q7ZeEtH9/x/FRP6:::::::
sshd:!*:19746::::::
```

If using Method 1, don't forget to flash the modified firmware image onto the Limelight as shown [here](#how-to-flash-firmware).

Done! You now have root access to the Limelight.


# Hardware
The Limelight 3A is really just a Raspberry Pi CM4 Lite module with 1GB of RAM and 8GB of onboard EMMC storage on a simple carrier board that has a camera attached.

The camera is an OV5647 module from the Chinese manufacturer SincereFirst, model no. SF-C5014OV-827B. It is labeled as such:
```
SF-AOV
5647-82
7B V1.1
```
The camera driver is modified on the Limelight's firmware image, meaning you can not just run Raspbian - the open source OV5647 driver does not work with this module. A quick decompilcation of the driver shows that it might be something related to power management.

The Limelight 3A has two LEDs:
- The yellow LED is connected to GPIO 4
- The green LED is connected to GPIO 5
  
The LED GPIO pins are set up as Output, Pull Up, High as default. The pin value is inverted - high means LED off

## Performance, overclocking & overheating issues
The CPU is directly attached to the aluminum casing using a head pad meaning it's got decent enough cooling to be overclocked to squeeze more performance out of it. 2.05 GHz worked great for us, and would be fine for at least 5-10 minutes of the CPU running at full utilization until the casing got too hot to touch. You may find out more about overclocking the CM4 [here](https://www.jeffgeerling.com/blog/2020/overclocking-raspberry-pi-compute-module-4).

While developing, you may shut down the Limelight's Visionserver to save on CPU power and heat: `sudo systemctl stop limelight_visionserver`.


# The Limelight Visionserver
The Limelight Visionserver is the main program running the Limelight's camera interface, web server, communication to the Control Hub, vision inference models, etc.

You may find out more about the Visionserver [here](https://www.chiefdelphi.com/uploads/short-url/414FkMFIfllCvDSIVBiesgLFTlS.pdf) (it's from 2019, but most of the things are still true, credit to FRC 696).

In general, these are the most important facts:
- The raw camera stream can be accessed on HTTP port 5802, and the camera stream with overlays (FPS counter, pipelines, etc.) on HTTP port 5800.
- The web interface runs on HTTP port 5801.
- A websocket server runs on 5805. Through it you may get real time detection information, crosshair info, etc.


# How to get packages & dependencies on the Limelight
Getting dependencies on the Limelight isn't as straightforward as it seems at first. The firmware image does not have SSL, meaning that even if you forward your internet connection it won't be able to pull most (if not all) package libraries (including Python's pip). 

## System packages
To work around this issue for system packages, I just downloaded the appropriate .deb package files from the Debian package repository on my local machine, and used `$ python3 -m http.server` to start a local HTTP server and `wget` on the Limelight to pull the files onto it. It's not the best way, and it's a pain for packages that require many dependencies, but it gets the job done.

## Python packages
To pull Python packages, I created a simple script in Python that acts as a sort of proxy to pull the packages from HTTPS sources. You can find the script in [`scripts/pip_proxy.py`](https://github.com/Vilnius-Lyceum-Robotics/limelight-3a-mod/scripts/pip_proxy.py) in this repository. # TODO upload script.

After running the script on your local machine, you may pull pip packages normally by running `$ sudo pip install --index-url http://PC_IP:8000/simple/ PACKAGE`. Keep in mind that `pip` is not installed by default, but running `$ sudo python get-pip.py` will install it.

Remember that the Python SnapScript interface on the Limelight runs on `root`, so if you are planning to install additional Python packages for use via the Visionserver, you should install them as `root` aswell.
