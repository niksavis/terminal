# Terminal Cheat Sheet

Practical Linux/Unix commands and shortcuts organized by use case. These work in WSL Ubuntu, macOS, and most Linux terminals. Windows-native shells (PowerShell/CMD) differ; use WSL in WezTerm for the commands below. Risky commands are marked with ⚠️.

## WezTerm Shortcuts (Linux-style)

- New tab: `Ctrl + Shift + T`
- Close tab: `Ctrl + Shift + W`
- Close window: `Ctrl + Shift + Q`
- Copy selection: `Ctrl + Shift + C`
- Paste: `Ctrl + Shift + V`
- Split horizontal (direct): `Ctrl + Alt + backslash`
- Split vertical (direct): `Ctrl + Alt + -`
- Close pane (direct): `Ctrl + Alt + X`
- Split vertical: `Ctrl + A` then `-` or `s`
- Split horizontal: `Ctrl + A` then `backslash`, `pipe`, or `v`
- Close pane: `Ctrl + A` then `x`

`Ctrl + A` is a leader key with a 3-second timeout: press and release it, then press the second key.

## Navigation

| Command           | Description                                     |
| ----------------- | ----------------------------------------------- |
| `pwd`             | Print working directory (show current location) |
| `cd <dir>`        | Change directory                                |
| `cd -`            | Go back to the previous directory               |
| `cd ~` or `cd`    | Go to home directory                            |
| `cd ..`           | Go up one directory                             |
| `pushd <dir>`     | Push directory onto stack                       |
| `popd`            | Pop directory from stack                        |
| `ls`              | List directory contents                         |
| `ls -la`          | List all files with details                     |
| `ls -lh`          | List with human-readable file sizes             |
| `ls -R`           | List recursively                                |
| `ls --color=auto` | Colorize output                                 |

## File Operations

| Command                 | Description                                             |
| ----------------------- | ------------------------------------------------------- |
| `touch <file>`          | Create a new file or update timestamp                   |
| `mkdir <dir>`           | Create a new directory                                  |
| `mkdir -p a/b/c`        | Create nested directories                               |
| `cp <src> <dst>`        | Copy a file                                             |
| `cp -r <src> <dst>`     | Copy a directory recursively                            |
| `mv <src> <dst>`        | Move or rename a file                                   |
| `rm <file>`             | Remove a file                                           |
| `rm -i <file>`          | Remove with confirmation                                |
| `rm -r <dir>`           | (!) Remove a directory recursively                      |
| `rm -rf <dir>`          | (!) Force-remove recursively - use with extreme caution |
| `rmdir <dir>`           | Remove an empty directory                               |
| `ln -s <target> <link>` | Create a symbolic link                                  |
| `cmp <file1> <file2>`   | Compare two files byte by byte                          |
| `diff <file1> <file2>`  | Show differences between two files                      |

## File Viewing

| Command             | Description                                                                 |
| ------------------- | --------------------------------------------------------------------------- |
| `cat <file>`        | Display file contents                                                       |
| `less <file>`       | View file with a pager (`j`/`k` scroll, `f`/`b` page, `/` search, `q` quit) |
| `head <file>`       | Show first 10 lines                                                         |
| `head -n 20 <file>` | Show first 20 lines                                                         |
| `tail <file>`       | Show last 10 lines                                                          |
| `tail -f <file>`    | Follow file changes in real time                                            |
| `nano <file>`       | Edit file with nano                                                         |
| `vim <file>`        | Edit file with Vim (`i` insert, `Esc` normal, `:wq` save and quit)          |

## Text & Output

| Command                       | Description                                  |
| ----------------------------- | -------------------------------------------- |
| `echo "text"`                 | Print text to terminal                       |
| `echo "text" > file`          | Overwrite file with text                     |
| `echo "text" >> file`         | Append text to file                          |
| `grep <pattern>`              | Search for a pattern in text or piped output |
| `grep -r "text" <dir>`        | Search recursively in directory              |
| `grep -i "text"`              | Case-insensitive search                      |
| `grep -n "text"`              | Show line numbers                            |
| `grep -v "text"`              | Invert match                                 |
| `awk '{print $5, $9}'`        | Print specific columns from output           |
| `sed 's/old/new/g' <file>`    | Replace text in output                       |
| `sed -i 's/old/new/g' <file>` | Replace text in place                        |
| `sort <file>`                 | Sort lines                                   |
| `uniq <file>`                 | Remove duplicate lines                       |
| `wc <file>`                   | Count lines, words, and bytes                |
| `cut -d: -f1 <file>`          | Cut columns by delimiter                     |
| `tr 'a-z' 'A-Z'`              | Translate characters                         |
| `jq`                          | Pretty-print and query JSON                  |
| `curl <url>`                  | Download or interact with URLs/APIs          |
| `wget <url>`                  | Download a file from the internet            |

## Permissions & Execution

| Command                       | Description                                     |
| ----------------------------- | ----------------------------------------------- |
| `chmod +x <file>`             | Make a file executable                          |
| `chmod 755 <file>`            | Set permissions to rwxr-xr-x                    |
| `chown <user>:<group> <file>` | Change file owner and group                     |
| `which <command>`             | Show path to a command executable               |
| `whereis <command>`           | Show executable, source, and man page locations |
| `file <file>`                 | Determine file type                             |
| `stat <file>`                 | Display file status                             |
| `man <command>`               | Open manual page for a command                  |
| `whatis <command>`            | Show a short summary of a command               |
| `alias name='command'`        | Create a command shortcut                       |

## Users & System

| Command                                               | Description                                                                 |
| ----------------------------------------------------- | --------------------------------------------------------------------------- |
| `whoami`                                              | Show current username                                                       |
| `id`                                                  | Show user ID and groups                                                     |
| `sudo <command>`                                      | Run command with superuser privileges                                       |
| `adduser <username>`                                  | Add a new user                                                              |
| `useradd <username>`                                  | Add a new user (low-level)                                                  |
| `su <username>`                                       | Switch to another user                                                      |
| `exit`                                                | Exit current shell or user session                                          |
| `sudo userdel -r <username>`                          | (!) Remove a user and home directory                                        |
| `passwd`                                              | Change your password                                                        |
| `uname -a`                                            | Show system information                                                     |
| `hostname`                                            | Show hostname                                                               |
| `uptime`                                              | Show system uptime                                                          |
| `neofetch`                                            | Show system info in a nice format                                           |
| `ip addr show`                                        | Show network/IP addresses (WSL/Linux; use `ipconfig` in Windows PowerShell) |
| `ping <host>`                                         | Check if a host is reachable                                                |
| `free -h`                                             | Show memory usage (human-readable)                                          |
| `df -h`                                               | Show disk usage (human-readable)                                            |
| `du -h --max-depth=1`                                 | Show subdirectory sizes                                                     |
| `ps aux`                                              | Show all running processes                                                  |
| `pgrep <name>`                                        | Find process ID by name                                                     |
| `kill -9 <pid>`                                       | (!) Force kill a process by ID                                              |
| `pkill -f <name>`                                     | (!) Kill processes by name                                                  |
| `killall <name>`                                      | (!) Kill all processes by name                                              |
| `top`                                                 | Dynamic process viewer                                                      |
| `htop`                                                | Interactive process viewer                                                  |
| `systemctl status <service>`                          | Check service status                                                        |
| `systemctl start <service>`                           | Start a service                                                             |
| `systemctl stop <service>`                            | Stop a service                                                              |
| `systemctl restart <service>`                         | Restart a service                                                           |
| `systemctl list-units --type=service --state=running` | List running services                                                       |

## Package Management (Debian/Ubuntu)

| Command                      | Description                |
| ---------------------------- | -------------------------- |
| `sudo apt update`            | Update package lists       |
| `sudo apt install <package>` | Install a package          |
| `sudo apt remove <package>`  | Remove a package           |
| `sudo apt upgrade`           | Upgrade installed packages |

## Archives & Search

| Command                            | Description                                |
| ---------------------------------- | ------------------------------------------ |
| `zip -r <archive>.zip <dir>`       | Compress a directory into a zip            |
| `unzip <archive>.zip`              | Extract a zip file                         |
| `unzip <archive>.zip -d <dir>`     | Extract to a specific directory            |
| `tar -czvf <archive>.tar.gz <dir>` | Create a tar.gz archive                    |
| `tar -xzvf <archive>.tar.gz`       | Extract a tar.gz archive                   |
| `find <path> -name "*.jpg"`        | Find files by name                         |
| `find <path> -type d -name "dev"`  | Find directories by name                   |
| `locate <name>`                    | Quick file search (uses prebuilt database) |

## Network & Remote

| Command                      | Description                    |
| ---------------------------- | ------------------------------ |
| `curl <url>`                 | Transfer data from/to a URL    |
| `wget <url>`                 | Download a file                |
| `ping <host>`                | Test connectivity              |
| `dig <domain>`               | DNS lookup                     |
| `ssh user@host`              | Connect to remote host via SSH |
| `scp <file> user@host:/path` | Secure copy to remote host     |
| `rsync -avz <src> <dst>`     | Sync files efficiently         |
| `ss -tulpn`                  | Show listening ports           |
| `lsof -i :80`                | Show what is using port 80     |

## Background Jobs

| Command       | Description                        |
| ------------- | ---------------------------------- |
| `cmd &`       | Run command in background          |
| `bg`          | Resume suspended job in background |
| `fg`          | Bring background job to foreground |
| `jobs`        | List background jobs               |
| `nohup cmd &` | Run command immune to hangups      |

## History & Shortcuts

| Shortcut    | Description                          |
| ----------- | ------------------------------------ |
| `Ctrl + L`  | Clear screen                         |
| `Ctrl + A`  | Move cursor to start of line         |
| `Ctrl + E`  | Move cursor to end of line           |
| `Ctrl + C`  | Interrupt current command            |
| `Ctrl + D`  | Exit shell (send EOF)                |
| `↑` / `↓`   | Cycle through previous/next command  |
| `Tab`       | Autocomplete file or directory names |
| `history`   | Show command history                 |
| `history 1` | Show full command history (in zsh)   |
| `exit`      | Close the terminal                   |

## Pipes & Redirection

| Operator     | Description                             |
| ------------ | --------------------------------------- |
| `\|`         | Pipe output of one command into another |
| `>`          | Redirect output to a file (overwrite)   |
| `>>`         | Redirect output to a file (append)      |
| `2>&1`       | Redirect stderr to stdout               |
| `tee <file>` | Write output to file and stdout         |
| `xargs`      | Build arguments from stdin              |

## Hardware & Disk Info

| Command             | Description                             |
| ------------------- | --------------------------------------- |
| `lscpu`             | Show CPU information                    |
| `lsblk`             | List block devices                      |
| `lspci -tv`         | Show PCI devices in a tree              |
| `lsusb -tv`         | Show USB devices in a tree              |
| `lshw`              | List hardware configuration             |
| `cat /proc/cpuinfo` | Detailed CPU info                       |
| `cat /proc/meminfo` | Detailed memory info                    |
| `free -h`           | Show free and used memory               |
| `df -h`             | Show disk space usage                   |
| `df -i`             | Show free inodes                        |
| `du -sh`            | Show total size of current directory    |
| `du -ah`            | Show sizes of all files and directories |
| `fdisk -l`          | List disk partitions                    |
| `mount`             | Show mounted file systems               |
| `findmnt`           | Show target mount points                |

## File Compression

| Command                             | Description                      |
| ----------------------------------- | -------------------------------- |
| `tar cf archive.tar <file/dir>`     | Create an uncompressed archive   |
| `tar xf archive.tar`                | Extract a tar archive            |
| `tar czf archive.tar.gz <file/dir>` | Create a gzip-compressed archive |
| `tar xzf archive.tar.gz`            | Extract a .tar.gz archive        |
| `gzip <file>`                       | Compress a file with gzip        |
| `gunzip <file.gz>`                  | Decompress a gzip file           |
| `bzip2 <file>`                      | Compress a file with bzip2       |
| `bunzip2 <file.bz2>`                | Decompress a bzip2 file          |
| `zip -r archive.zip <dir>`          | Create a zip archive             |
| `unzip archive.zip`                 | Extract a zip archive            |

## Shell Variables

| Command             | Description                        |
| ------------------- | ---------------------------------- |
| `export VAR=value`  | Set an environment variable        |
| `declare VAR=value` | Declare a shell variable           |
| `let "VAR=1+2"`     | Assign an integer value            |
| `set`               | List all shell variables/functions |
| `unset VAR`         | Remove a variable                  |
| `echo $VAR`         | Display a variable value           |

## Shell Command Management

| Command                | Description                                |
| ---------------------- | ------------------------------------------ |
| `alias name='command'` | Create a command shortcut                  |
| `unalias name`         | Remove an alias                            |
| `watch -n 2 <command>` | Run a command repeatedly every N seconds   |
| `sleep 5 && <command>` | Delay a command                            |
| `at <time>`            | Schedule a one-time job (Ctrl+D to finish) |
| `man <command>`        | Open the manual page                       |
| `whatis <command>`     | Show a short summary                       |
| `history`              | Show command history                       |
| `source <file>`        | Execute a file in the current shell        |
| `clear`                | Clear the terminal screen                  |
| `!!`                   | Run the last command again                 |

## More Keyboard Shortcuts

| Shortcut   | Description                          |
| ---------- | ------------------------------------ |
| `Ctrl + W` | Cut the word before the cursor       |
| `Ctrl + U` | Cut the line before the cursor       |
| `Ctrl + K` | Cut the line after the cursor        |
| `Ctrl + Y` | Paste the cut text                   |
| `Ctrl + R` | Search command history interactively |
| `Ctrl + O` | Run the recalled history command     |
| `Ctrl + G` | Exit history search without running  |
| `Ctrl + Z` | Suspend the current process          |

## Safety Notes

- ⚠️ `rm -rf` can destroy your system. Double-check paths before running.
- ⚠️ `kill -9`, `pkill -f`, and `killall` terminate processes immediately without cleanup.
- ⚠️ `sudo userdel -r` permanently deletes a user and their home directory.
- Always use `rm -i` or review commands with `--dry-run` equivalents when available.
