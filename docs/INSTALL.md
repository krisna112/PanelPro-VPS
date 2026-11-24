# Installation and website deployment

## Requirements

Use a Linux VPS with systemd, root access, and Python 3.10 or later. The package
installer targets Ubuntu 22.04+ and Debian 12+. On RHEL-family hosts, the
installer uses the distro's Python 3.11 packages and supports the Nginx option.
The bundled PHP-FPM and MariaDB setup uses Debian-family packages and sockets.

## Install on a fresh VPS

For direct browser access, point a dedicated hostname such as
`panel.example.com` at the VPS with an A record. Allow inbound TCP ports 80
and 443 through the VPS and provider firewalls so Nginx can serve websites and
Let's Encrypt can validate the hostname. Add an AAAA record only if IPv6
reaches the same VPS.

```bash
git clone https://github.com/krisna112/PanelPro-VPS.git
cd PanelPro-VPS
sudo bash scripts/install.sh
```

The installer asks for the panel hostname, your Let's Encrypt email, and the
web stack. Choose Nginx for static sites and reverse proxies or choose the
PHP stack for Nginx, PHP-FPM, and MariaDB on Ubuntu or Debian. On a fresh
installation, enter the administrator username and password when prompted.
The installer hides the password while you type and asks you to confirm it.
After the service starts and the certificate is issued, open the full HTTPS login URL
printed by the installer. The panel backend uses port 21000 on loopback and
website traffic uses ports 80 and 443. Certbot reloads Nginx when it renews the
panel certificate.

For unattended setup, pass the values on the command line. With `--domain`, the
installer defaults to Nginx. Use `--stack php` for PHP-FPM and MariaDB or
`--stack none` to use existing Nginx and Certbot. On RHEL-family hosts, install
Certbot separately before setting up the domain.

```bash
sudo bash scripts/install.sh --domain panel.example.com --email admin@example.com
```

Use `--interactive` to open the wizard when supplying other options. Run
with just `--non-interactive` for a panel-only installation with the default
local listener. If you leave the hostname blank in the wizard or if domain setup
fails, the installer prints the local URL and SSH tunnel command.

Sign in with the credentials you entered. Unattended installations generate
an initial admin password in `/usr/local/panelpro/data/admin_credentials.txt`.
Delete that file after saving the generated credentials. The path follows
your `--dir` option.

## PHP-FPM and phpMyAdmin

On a fresh Debian or Ubuntu installation that provisions Nginx, the installer
also sets up phpMyAdmin. It installs the distribution's PHP-FPM and reuses an
existing local MySQL or MariaDB installation, or installs MariaDB when needed.
Use `--skip-phpmyadmin` when you want to omit this setup. With `--stack none`,
install phpMyAdmin once Nginx is installed and running.

On an existing VPS, choose **App Store → phpMyAdmin → Install** after updating
PanelPro. You can also run `sudo panelpro install-app phpmyadmin` on the VPS.
In the Installed list, use **SSH access** to view the tunnel command. From your
workstation, replace `user@IP_VPS` with your SSH login and address.

```bash
ssh -N -L 8881:127.0.0.1:8881 user@IP_VPS
```

While the tunnel is open, visit `http://127.0.0.1:8881/` and sign in with a
MySQL or MariaDB account. Create one under **Databases** and grant access to
the database you want to manage. The App Store's **Remove access** action
removes the PanelPro Nginx listener and keeps the database and shared packages.

**App Store → PHP-FPM** and the **PHP** page use the same installer. Choose
the distribution default or select a version available in the server's
repositories. The new version becomes selectable for sites after its FPM
service starts and the Unix socket is ready.

## Terminal administration

After installing or running `scripts/update.sh`, open the menu on the VPS.

```bash
sudo panelpro menu
```

The menu shows the login URL, admin usernames, and service status. Use it to
start, stop, or restart the service, change the backend port or login path,
change a login username or password, set up the HTTPS domain, or view recent logs. Changing
the backend port through the menu updates the managed HTTPS route and checks
the new listener before reporting success.

Choose option **10** to change credentials. Enter the account's current
username, then enter a new username and a new password. Press Enter at either
new-value prompt to keep that value. The console hides the password and asks
you to confirm it. After saving, sign in again using the resulting username and
password at your panel login URL. Changes take effect as soon as they are saved.

If `/usr/local/bin/panelpro` is already in use, run
`sudo /usr/local/panelpro/venv/bin/panelpro menu` with your install directory.

## Add an HTTPS login domain to an existing installation

From the current checkout on the VPS, update PanelPro and run `setup-domain`.
Use a hostname dedicated to panel access. This keeps the existing account,
entry path, and websites.

```bash
git pull --ff-only
sudo bash scripts/update.sh
sudo /usr/local/panelpro/venv/bin/panelpro setup-domain panel.example.com --email admin@example.com
```

The command uses the running panel's configured port and writes
`panelpro-panel.conf` in the Nginx include directory. Run it again to repair
or retry domain setup. A failed attempt restores the previous Nginx config.

## Publish a website

1. Point your domain's A record at the VPS. Set an AAAA record if the VPS
   serves IPv6. Add records for each alias you intend to serve.
2. In **Websites → Tambah Website**, pick an active webserver and the
   deployment type.
   - **Website statis** serves the contents of the folder shown below the
     domain. Use the folder link to upload a static HTML project or the
     output of a frontend build. Replace the generated `index.html`.
   - **PHP-FPM** routes PHP requests to the selected running FPM version.
     Upload the public entry point and assets to the website folder. Keep
     application secrets and any private files outside that folder. The
     optional database step provisions a local MySQL or MariaDB database and
     user and returns its credentials when creation succeeds.
   - **Reverse proxy** connects to an application already listening on the VPS.
     Start your Node.js, Python, or other application under a service manager.
     Use its internal URL, for example `http://127.0.0.1:3000`.
3. Open **SSL / HTTPS** on the website row, then select **Let's Encrypt**.
   The panel pre-fills the domains and website folder. HTTP-01 requires the
   requested domains to reach this website over port 80. For wildcard
   certificates use DNS-01 and install the appropriate Certbot plugin.
4. Test HTTPS for the primary domain and aliases before enabling
   **Paksa HTTPS**. Check the per-site access and error logs if a request fails.

With Apache on Debian or Ubuntu, enable the modules used by your deployment
(`ssl` for HTTPS, `proxy` with `proxy_http` for reverse proxy, and `proxy_fcgi`
for PHP-FPM) and restart Apache before creating sites. Admins can edit vhosts on
active sites. Changing website settings regenerates the managed configuration.

## Update and diagnostics

```bash
sudo bash scripts/update.sh
sudo /usr/local/panelpro/venv/bin/panelpro doctor
sudo journalctl -u panelpro -n 60
```

Run the updater from the newer checkout. Set `PANELPRO_HOME` when using a
custom install path. If a previous install left the systemd launcher missing,
rerun the installer with your chosen directory and port to repair it.

```bash
sudo bash scripts/uninstall.sh           # keep stored data
sudo bash scripts/uninstall.sh --purge   # also delete the install directory
```

| CLI command | Purpose |
| --- | --- |
| `panelpro start [--host H] [--port P] [--dev]` | Run the server |
| `panelpro menu` | Open the terminal administration menu |
| `panelpro setup-admin` | Set the first admin username and password interactively |
| `panelpro change-credentials [--username NAME]` | Update an existing account's username or password |
| `panelpro reset-password [--username admin]` | Generate a password and revoke existing sessions |
| `panelpro set-port 21000` | Change the listener port, then restart the panel |
| `panelpro set-entry my-secret-path` | Change the private entry path |
| `panelpro setup-domain panel.example.com --email admin@example.com` | Publish the panel login over HTTPS through Nginx |
| `panelpro backup-panel` | Archive the panel database and secrets |
| `panelpro doctor` | Inspect the platform, database and available tools |
| `panelpro version` | Print the installed version |

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PANELPRO_HOME=./runtime PANELPRO_WWW_ROOT=./runtime/www python -m panelpro start --dev
```

On Windows, use `.venv\Scripts\Activate.ps1` and set `$env:PANELPRO_HOME`
before running the launcher. Install frontend libraries locally with
`bash scripts/vendor_assets.sh` when developing offline.

```bash
pytest
ruff check panelpro
```
