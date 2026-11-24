# Lab run: AAP 2.4 RPM to AAP 2.6 RPM

Course: [Fast-track Ansible Automation Platform Migration](https://redhatquickcourses.github.io/aap-migration/aap-migration/1/index.html), chapter 1.

Commands are listed in the order they were run on the lab bastion. Download URLs are not stored here.

## Installer command

Every later `setup.sh` run starts a new log, then uses full Ansible verbosity. Red Hat Support needs that `setup.log` when an install fails, and it has to contain only the run being reviewed.

```bash
if [ -e setup.log ]; then
  mv setup.log "setup.log.$(date +%Y%m%d%H%M%S)"
fi
./setup.sh -i inventory-growth -vvvvv
```

Steps 10 and 13 below were run as `./setup.sh -i inventory-growth` without `-vvvvv`. The successful log is the one measured in step 14.

## Session

| Step | Command | Result |
|---|---|---|
| 1 | SSH to the lab bastion | Session open. The exact `ssh` arguments were not captured. |
| 2 | `getent hosts gateway.lab controller.lab hub.lab database.lab` | All four names resolved. |
| 3 | Download page for the AAP 2.6 RPM setup bundle | File selected: `ansible-automation-platform-setup-bundle-2.6-9.2-x86_64.tar.gz`. The first link was the containerized bundle and was not used. |
| 4 | `wget -O aap.tar.gz "<quoted RPM setup-bundle URL>"` | Download finished. |
| 5 | `ls -lh aap.tar.gz` | `-rw-r--r--. 1 lab-user users 3.4G Nov  3 20:51 aap.tar.gz` |
| 6 | `tar -xvf aap.tar.gz` | Extract completed. Directory: `ansible-automation-platform-setup-bundle-2.6-9.2-x86_64`. |
| 7 | `cd ansible-automation-platform-setup-bundle-2.6-9.2-x86_64` | Prompt is now in that directory. |
| 8 | `grep -n -E 'set your own\|example.org' inventory-growth` | Placeholders are on lines 12, 17, 25, 30, 35, 40, and 53–76. |
| 9 | `cp -p inventory-growth inventory-growth.bak`, then a Python edit of `inventory-growth` | Updated. Backup is `inventory-growth.bak`. No `example.org` or `<set your own>` remains. |

## Inventory after step 9

| Group or variable | Value |
|---|---|
| `[automationgateway]` | `gateway.lab` |
| `[automationcontroller]` | `controller.lab` |
| `[execution_nodes]` | Empty. `exec.example.org` was removed. |
| `[automationhub]` | `hub.lab` |
| `[automationedacontroller]` | Empty. `eda.example.org` was removed. This lab has no EDA host. |
| `[database]` | `database.lab` |
| `*_password` | `redhat` |
| `*_pg_host` and `pg_host` | `database.lab` |
| `ansible_become` | `true`, in a second `[all:vars]` block at the end of the file |

## Installer

| Step | Command | Result |
|---|---|---|
| 10 | `./setup.sh -i inventory-growth` | Failed in preflight. All four hosts report Red Hat Enterprise Linux 9.5. This 2.6 setup bundle requires 9.6 or later. Play recap: each host `failed=1`, and each host also has `changed=1`. Setup log: `./setup.log`. |
| 11 | `awk` over `setup.log` for `changed:` lines, then `ssh` to each lab host for `/etc/redhat-release`, `subscription-manager release --show`, and `dnf repoquery redhat-release` | The only changed task was `subscription-manager identity`, which reads registration and exits 0. Each host is Red Hat Enterprise Linux 9.5 (Plow). Release is not set. Available package: `redhat-release-9.7-0.7.el9`. Subscription environment: `Library/rhel-8-and-9-latest`. |
| 12 | `ssh` to each lab host: `sudo dnf update -y && sudo reboot` | Update completed and the hosts rebooted. The visible end of the transaction installed `redhat-release-9.7-0.7.el9` and kernel `5.14.0-611.24.1.el9_7`. `getent hosts` still resolves all four names, and SSH to the hosts works. |
| 13 | Release check on the four hosts, then `./setup.sh -i inventory-growth` | Completed successfully. Message: `The setup process completed successfully.` Play recap, all `failed=0`: controller `ok=376 changed=108 skipped=228 ignored=2`; database `ok=87 changed=16 skipped=63 ignored=1`; gateway `ok=209 changed=83 skipped=197 ignored=3`; hub `ok=1233 changed=185 skipped=405 ignored=2`. |
| 14 | Python scan of `setup.log` for Ansible task `start` and `end` times | First task `2026-11-05 18:57:11`, last task `2026-11-05 19:44:46`. Elapsed time **47m 34s**. An earlier scan also matched a `2036-10-29` date in the log and is not the install time. |
| 15 | `ssh gateway.lab`, then `cat external_ip` | `148.62.104.6` |
| 16 | Browse to `https://148.62.104.6/` and sign in as `admin` | Login succeeded. The AAP 2.6 UI is up. |

## Chapter 2: migration artifact

| Step | Command | Result |
|---|---|---|
| 17 | `getent hosts container.lab`, then the artifact script on `gateway.lab` | `container.lab` is `10.130.96.120`. The script stopped with `Host key verification failed` on the first SSH from `gateway.lab` to `hub.lab`. No tar file was created. The gateway had not connected to the hub or controller before, so those host keys were not in its `known_hosts`. |
| 18 | Same artifact script, with first-use host key acceptance | `hub.lab` was added to the gateway’s `known_hosts`. Login then failed: `Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password)`. The gateway’s `lab-user` has no key for the hub. No tar file was created. |
| 19 | Artifact script run on the bastion | Secrets and manifest were written. Versions: controller `4.7.18`, hub `4.11.15`, gateway `2.6.20261019`. Controller database `awx`, hub database `automationhub`. The gateway database name was read from the wrong `NAME` field. `dnf install postgresql` installed client 13.23, and `pg_dump` aborted because the server is PostgreSQL 15.15. No dump files and no tar were created. The `pkg_resources` line is a warning from `awx-manage`, not a failure. |
| 20 | Repair script for the gateway database name and a PostgreSQL 15 dump | `migration_artifact/` had been removed first. The repair stopped with `FileNotFoundError` for `secrets.yml`. No tar was created. |
| 21 | Rebuild the artifact on the bastion and dump with `database.lab`’s PostgreSQL 15 client | Succeeded. `sha256sum --check migration_artifact.tar.sha256` reported `migration_artifact.tar: OK`. |

## Artifact from step 21

Built in `/home/lab-user` on the bastion. Dumps were taken on `database.lab` with `/usr/bin/pg_dump`, `pg_dump (PostgreSQL) 15.15`.

| Item | Value |
|---|---|
| Controller | `4.7.18`, database `awx`, dump `2.6M` |
| Gateway | `2.6.20261019`, database `automationgateway`, dump `307K` |
| Hub | `4.11.15`, database `automationhub`, dump `8.5M` |
| `migration_artifact.tar` | `12M` |
| `./controller/automationcontroller.pgc` | `51c0c23e612c61f2d0612d57b4946ab81e3d3a41d98f7372cc1aba18a2c727d3` |
| `./hub/automationhub.pgc` | `163a3eb64350de6b2c4d57e43bb3e37a71f5011bc9d2a5c49c102fce343b5460` |
| `./gateway/automationgateway.pgc` | `b6bc225489d9512fefe76e178b83a533b20e058d223c2cbd612ea2a82f6567b4` |

`secrets.yml` is in the archive and is not copied here. The `pkg_resources` line during collection was a warning from `awx-manage`.

## Chapter 3: containerized 2.6

| Step | Command | Result |
|---|---|---|
| 22 | `mv aap.tar.gz aap26rpm.tar.gz` on the bastion | The RPM setup bundle is now `aap26rpm.tar.gz`. The extracted directory `ansible-automation-platform-setup-bundle-2.6-9.2-x86_64` is unchanged. |
| 23 | `wget -O aap26containerized.tar.gz "<quoted containerized setup-bundle URL>"` on the bastion | Saved `4492149966/4492149966` bytes at 20:33:32, 10.6 MB/s. File: `ansible-automation-platform-containerized-setup-bundle-2.6-14.2-x86_64.tar.gz`. The SSH session then dropped and was opened again. `ls` on the bastion shows `aap26containerized.tar.gz`. |
| 24 | `scp` the artifact, its checksum, and `aap26containerized.tar.gz` to `container.lab`, then check them and `dnf install` the course utilities | Copy finished. Artifact checksum matched and the bundle is `4284MB`. `dnf` then failed: `container.lab` is not registered and `/etc/yum.repos.d` has no enabled repositories. |
| 25 | Check `container.lab` release, subscription, and files; look on the bastion for a registration helper | Bundle size is `4492149966`. Artifact files are present. Release is Red Hat Enterprise Linux 9.5 (Plow). `container.lab` is not registered and has no repositories. The bastion consumer profile has been deleted on the entitlement server. No activation-key file was found by name. |
| 26 | Search the lab hosts for an activation key and register `container.lab` | The search program was executed by bash instead of Python. Every host reported `import: command not found`. No registration was attempted. |
| 27 | Python search for an activation key, then `subscription-manager register` on `container.lab` | Controller search matched the placeholder `NOT_LOGGING_PARAMETER`. Registration returned HTTP 404, activation key not found. `container.lab` is still unregistered. |
| 28 | `ssh container.lab` from the bastion | Login asked for a password. Session reached `[lab-user@container ~]$`. |
| 29 | `subscription-manager register` on `container.lab`, then copy registration from `controller.lab` and `dnf update` | Register reached `demosat-ha.infra.demo.redhat.com` and rejected the account. `controller.lab` then reported `This system is not yet registered`, so the script stopped before `dnf update`. Release is still Red Hat Enterprise Linux 9.5 (Plow). |
| 30 | `subscription-manager identity` and `dnf repolist` on `gateway.lab`, `hub.lab`, and `database.lab` | Gateway and database are not registered and list no repositories. Hub’s consumer profile was deleted on the server, but its local repo list still includes RHEL 9 BaseOS and AppStream. |

## Hosts from step 2

| Name | Address |
|---|---|
| gateway.lab | 10.130.96.124 |
| controller.lab | 10.130.96.121 |
| hub.lab | 10.130.96.125 |
| database.lab | 10.130.96.123 |
| container.lab | 10.130.96.120 |
