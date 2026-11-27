---
name: wake-gnome-desktop
description: Wake the GNOME desktop in the Ansible Control inventory over Wake-on-LAN and verify SSH access. Use when asked to wake that desktop or to recover access when it may be suspended.
---

# Wake the GNOME desktop

1. Find the `[desktop]` member whose `host_vars` sets `desktop_environment: gnome`. Read its SSH user and FQDN from `hosts`. Select the pfSense router in `[routers]` for the same site using the FQDN suffix. Try normal SSH with `BatchMode=yes` and a short `ConnectTimeout` first. Send a wake packet only when the operator has authorized waking the desktop.
2. On the router, use its native PHP configuration accessor to look up the two static mappings. Over SSH, pass PHP on standard input and load `/etc/inc/config.inc`, `/etc/inc/interfaces.inc`, and `/etc/inc/util.inc`. Iterate `array_keys(get_configured_interface_list())` and read only `config_get_path("dhcpd/{$interface}/staticmap", [])`. Match the Wi-Fi entry by the inventory alias and its resolved IPv4 address. Select the unique same-host mapping on a different interface whose hostname is the alias with an interface suffix. Stop if the target is ambiguous. Keep the MAC on the router and look up addresses again on every invocation.
3. Probe TCP port 22 from the router using the wired mapping's IP. If it answers, try the wired SSH route below before sending a packet. Otherwise validate the wired mapping's MAC and IPv4 address, then compute its VLAN broadcast address with `gen_subnet_max(get_interface_ip($interface), get_interface_subnet($interface))`. Run `/usr/local/bin/wol --ipaddr=<broadcast> <mac>` on the router. The controller's broadcast relay does not cover the tagged wired VLAN.
4. Allow about 15 seconds for resume and Wi-Fi reassociation, then retry normal SSH. If it still times out, try the wired route through the router. Keep the inventory FQDN as the host-key identity.

   ```sh
   ssh -o BatchMode=yes -o ConnectTimeout=7 -o StrictHostKeyChecking=yes \
     -o "HostKeyAlias=$desktop_fqdn" -o "HostName=$wired_ip" \
     -J "$router_destination" "$desktop_user@$desktop_fqdn" true
   ```

5. If both SSH routes still fail, send one fallback packet on the Wi-Fi mapping's subnet using the same broadcast calculation. Retry both routes with bounded timeouts. Report which path accepted SSH, or that a wake packet was sent and SSH remains unavailable. Packet transmission alone does not establish that the desktop resumed.

The wired interface needs `Wake-on: g` and `wakeonlan: true` in netplan. Wi-Fi uses `wakeonwlan: [magic_pkt]` and is less reliable. If neither path wakes the desktop, check whether the firmware permits PCIe wake from S3. Firmware updates can reset **Resume By PCI-E Device** and **ErP Ready**. Leave firmware and network configuration changes to a separate request.
