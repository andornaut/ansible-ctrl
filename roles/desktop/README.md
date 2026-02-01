# ansible-role-desktop

Configures a Linux desktop environment with common applications on Ubuntu.

## Usage

```bash
make desktop

ansible-playbook --ask-become-pass desktop.yml --tags display-manager
ansible-playbook --ask-become-pass desktop.yml --tags firefox
```

## Variables

See [defaults/main.yml](./defaults/main.yml).
