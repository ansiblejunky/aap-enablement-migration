# Migration wizard

Local page that logs into an automation controller, reads `/api/v2/`, and walks Red Hat delivery folks from this AAP 2.4 lab to a supported upgrade or migration target.

The page cannot call a controller on another host by itself. Controller hosts do not send CORS headers for a browser page, and this branch is not the GitHub Pages deploy branch. `wizard/server.py` binds to `127.0.0.1`, serves the page, and proxies only the controller URL typed into the form.

## Run

From the repository root, with Python 3 and no extra packages:

```bash
python3 wizard/server.py
```

Open http://127.0.0.1:8765/.

Optional flags: `--host 127.0.0.1` and `--port 8765`. The process refuses to bind any other host.

## What the six steps do

1. **Connect.** Controller URL, a bearer token or a username and password, and TLS verification. TLS verification stays on unless you clear it for a lab certificate.
2. **Findings.** Version and instances from `/api/v2/ping/`. If that path returns 404, the page tries `/api/controller/v2/ping/` and treats the URL as a platform gateway, which is not this lab’s source. It also reads the **AAP Migration Lab** organization and project, job-template and execution-environment counts, and LDAP, SAML, and OIDC settings when the login can see them.
3. **Pre-check.** Scores installer preflight before a target is chosen. The controller version comes from the API. RHEL version, CPU, memory, disk, `noexec` mounts, hostname, subscription, custom virtual environments, schema, and firewall ports are entered from the hosts. The port list is different for AAP 2.4 RPM, AAP 2.6 RPM growth, and AAP 2.6 RPM enterprise. The wizard does not log in to those hosts and does not change them.
4. **Targets.** Supported, extra-step, and unsupported destinations for AAP 2.6, plus the sequenced path toward 2.7.
5. **Walkthrough.** Ordered steps for the target you pick. The wizard does not run the upgrade.
6. **Validate.** Reads the controller again. A loaded lab has the organization, the project, a successful project sync, and the job templates. Run it again after the move, against the target URL.

The controller API does not report installer type, RHEL major version, private automation hub, or Event-Driven Ansible. The findings step asks those four questions, and advice waits until they are answered.

Automation controller 4.4 and 4.5 are AAP 2.4, the same range `install-apd.yml` accepts. One control or hybrid node maps to a 2.6 growth topology. More than one maps to enterprise. Execution nodes do not change that result. Hop nodes are absent from ping.

## What the server will not do

- Bind beyond localhost.
- Forward anything except `GET` under `/api/` on the one connected origin.
- Follow a controller redirect.
- Write the username, password, or token to disk, or print the `Authorization` header.
- Change the controller. The browser holds the login in tab memory and sends it on each read.

## Checks

```bash
python3 -m unittest wizard.test_advise wizard.test_precheck wizard.test_server
```

Support rules are summarized from the AAP 2.6 upgrade documentation linked in each target. `wizard/advise.py` is the only decision module.

Further source discovery, readiness checks, and walkthrough diagrams are tracked in [BACKLOG.md](BACKLOG.md).
