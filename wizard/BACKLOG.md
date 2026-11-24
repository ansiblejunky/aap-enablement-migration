# Migration wizard backlog

The current page is a five-step layout: source login, findings, targets, walkthrough, and validation. It reads the automation controller API and then asks the operator for installer type, RHEL major version, private automation hub, and Event-Driven Ansible. The items below are the next product work. The layout stays.

## 1. Call the first step Source

The stepper says **Connect**, and the page title says **Connect to the source controller**. Both should say **Source**.

The login is the platform you are leaving, and that platform may be AAP 2.4, 2.6, or another release. On 2.4 the API is the automation controller at `/api/v2/`. On 2.5 and later the same URL often answers through the platform gateway at `/api/controller/v2/`. The heading and the step name should describe the source platform, and the login copy should accept either API.

## 2. Fill Findings from the platform

Findings should show the source, so the operator does not pick installer, operating system, hub, or EDA by hand. Advice can wait until those facts are known, and the questions go away once discovery is reliable.

The controller ping used today is only part of that picture. `/api/v2/ping/` lists control, hybrid, and execution instances and omits hop nodes. It does not report:

- Installer type: RPM, operator, or containerized
- RHEL major version, CPU, memory, and free space on each host
- Whether `/tmp` is mounted `noexec`
- How many automation hub nodes exist (one, two, or more), and the full mesh: control, execution, hop, and hub
- Whether Event-Driven Ansible is installed, and whether its database holds rulebooks, activations, or audit events
- Database version, and whether that database was upgraded on its own or its schema is unhealthy

Later releases add the gateway, so discovery has to follow whichever API answered and then call hub and EDA on their own services. Host facts (CPU, disk, mount options, Postgres) are not in the controller API. They need a read-only check on the source hosts, run from this same local wizard, with the results shown on Findings.

## 3. Require the latest minor before a migration

Patch the source to the latest minor of its current AAP release before any upgrade or migration. For the 2.4 line that is the latest `2.4.x`, where the third position is the minor. The same rule applies on later lines (`2.5.x`, `2.6.x`).

`/api/v2/ping/` reports the automation controller version (`4.4.z` or `4.5.z` on the 2.4 line), not the AAP product string `2.4.x`. The gate needs a maintained map from component versions (controller, hub, EDA, and gateway when present) to the AAP minor, plus a record of which minor is current for that line. Until the source matches that minor, Targets stays closed and the walkthrough’s first step is the in-place patch.

## 4. Decide whether the source is ready

The Pre-check step scores a ready, blocked, or incomplete result before Targets. It already covers the installer preflight that stopped the lab upgrade, plus the port list for the selected AAP version:

- RHEL minor version. AAP 2.6 RPM requires 9.6 or later, so 9.5 is blocked. AAP 2.4 RPM still accepts that host.
- CPU, memory, and disk minimums for the role.
- `noexec` on `/tmp`, `/var`, and `/var/tmp`.
- A hostname of `localhost`.
- Subscription registration, custom virtual environments, and `awx-manage migrate --check`.
- Automation controller 4.5 or newer for the 2.6 RPM installer.
- Firewall ports. AAP 2.6 RPM adds the platform gateway flows, including gateway to database `5432/tcp`. AAP 2.4 RPM has no gateway. Enterprise adds gateway-to-gateway `8443/tcp` and Redis `16379/tcp`.

The operator types the host measurements. The wizard does not yet open SSH and collect them. These checks are still not collected from the hosts:

- A database upgraded beyond the version that AAP release supports.
- Database schema or data health beyond the migrate check the operator reports.

Each failed check names the host or service, the value found, and the condition that has to change. The wizard still does not change the source.

## 5. Diagram the walkthrough

The walkthrough for a chosen target should show a high-level diagram of each major step and what that step needs: hosts, backup, temporary infrastructure, and the AAP version at the end of the step.

The RHEL 8 RPM path is the example to correct. Today the steps restore the backup onto RHEL 9 and treat the next action as the upgrade to 2.6. The diagram should show the same-version move first:

1. AAP 2.4 RPM on RHEL 8.
2. AAP 2.4 RPM on RHEL 9, restored onto temporary infrastructure. The platform version stays 2.4.
3. Upgrade that RHEL 9 deployment from 2.4 to the chosen target.

Other targets get the same treatment: one box per major step, with the version and the infrastructure that step requires, then the short procedure already written under the diagram.
