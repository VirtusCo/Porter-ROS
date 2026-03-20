# ROS 2 Distributions & Releases — Skill File

> Source: https://docs.ros.org/en/jazzy/Releases.html
> Distro: Jazzy Jalisco

---

## What is a Distribution?

A **versioned set of ROS packages**, akin to a Linux distribution. Once released:
- Core packages limited to **bug fixes and non-breaking improvements**.
- Higher-level packages have less strict rules (maintainer discretion).

---

## Distribution List

### Currently Supported

| Distribution | Codename | Release Date | EOL | Type | ROS Boss |
|---|---|---|---|---|---|
| **Kilted Kaiju** | kilted | May 23, 2025 | Dec 2026 | Non-LTS | Scott K Logan |
| **Jazzy Jalisco** | jazzy | May 23, 2024 | **May 2029** | **LTS** | Marco A. Gutiérrez |
| **Humble Hawksbill** | humble | May 23, 2022 | **May 2027** | **LTS** | Christophe Bédard / Audrow Nash |

### Future

| Distribution | Release Date | EOL |
|---|---|---|
| **Lyrical Luth** | May 2026 | May 2031 (LTS) |

### End-of-Life (Historical)

| Distribution | Release | EOL |
|---|---|---|
| Iron Irwini | May 2023 | Dec 2024 |
| Galactic Geochelone | May 2021 | Dec 2022 |
| Foxy Fitzroy | June 2020 | June 2023 |
| Eloquent Elusor | Nov 2019 | Nov 2020 |
| Dashing Diademata | May 2019 | May 2021 |
| Crystal Clemmys | Dec 2018 | Dec 2019 |
| Bouncy Bolson | July 2018 | July 2019 |
| Ardent Apalone | Dec 2017 | Dec 2018 |

---

## Release Cadence

- **New release every year** on **May 23rd** (World Turtle Day 🐢).
- **LTS releases**: every other year, supported for **5 years**.
- **Non-LTS releases**: supported for ~**1.5 years**.

---

## Rolling Ridley

- Continuous rolling development distribution (since June 2020, REP 2002).
- **Two purposes**:
  1. Staging area for future stable distributions.
  2. Collection of most recent development releases.
- **Can have breaking changes** at any time — not for production.
- Packages released to Rolling are automatically released to future stable distros.

---

## Cross-Distribution Communication

- **NOT guaranteed** between distributions (e.g., Humble ↔ Iron).
- May or may not work, but **not supported**.
- Cross-vendor (single-distro) communication is also **NOT guaranteed**.

---

## Jazzy Jalisco Details

| Property | Value |
|---|---|
| **Codename** | jazzy |
| **Release** | May 23, 2024 |
| **EOL** | May 2029 |
| **Type** | LTS |
| **Ubuntu** | 24.04 Noble Numbat |
| **Python** | 3.12 |
| **CMake** | ≥ 3.22 |
| **C++** | C++17 |
| **Default RMW** | rmw_fastrtps_cpp |

---

## Choosing a Distribution

| Scenario | Recommendation |
|---|---|
| Production / deployed robots | **Latest LTS** (Jazzy or Humble) |
| Latest features, okay with changes | Rolling Ridley |
| Long-term support needed (5 yr) | LTS (Jazzy = May 2029) |
| Contributing to ROS 2 core | Rolling Ridley |
| Short-term project | Latest non-LTS (if features needed) |
