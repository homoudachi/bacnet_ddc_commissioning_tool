# macvlan BACnet lab (on-prem bench)

The default **`bacnet-dev`** profile uses **localhost UDP port maps** on a Docker **bridge** network. That is ideal for CI and laptops.

Some benches need controllers (or this repo’s Docker sim) to appear as **first-class IPv4 hosts on a physical LAN**. Docker **macvlan** attaches container interfaces directly to a parent interface.

## 1. Create a macvlan network on the host

Pick a **free subnet** on the LAN (coordinate with IT). Example: `192.168.40.0/24`, gateway `192.168.40.1`, parent `eth0`:

```bash
docker network create -d macvlan \
  --subnet=192.168.40.0/24 --gateway=192.168.40.1 \
  -o parent=eth0 bacnet_lab_macvlan
```

## 2. Export variables and start the example service

From the repository root:

```bash
export BACNET_MACVLAN_NETWORK=bacnet_lab_macvlan
export BACNET_MACVLAN_FCU_IP=192.168.40.20   # must be free on that subnet

docker compose -f docker/simulator/docker-compose.yml \
  -f docker/simulator/docker-compose.macvlan.example.yml \
  --profile bacnet-macvlan up -d --build
```

The example file (`docker/simulator/docker-compose.macvlan.example.yml`) runs **one** FCU-shaped sim. Copy or extend it for multiple devices, HRV profile, etc.

## 3. Point `site-controllers.csv` at the macvlan IPs

Set each controller row’s **`bacnet_ip`** to the container’s macvlan address and **`bacnet_port`** to **47808** (or whatever `BACNET_UDP_PORT` you set).

## 4. CI note

GitHub-hosted runners **do not** have your LAN parent interface; **do not** rely on macvlan in default CI. Use **`bacnet-dev`** or the **`bacnet-bbmd-lab`** profile for automated checks.
