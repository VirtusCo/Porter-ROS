# ROS 2 Release Process — Skill File

> Source: https://docs.ros.org/en/jazzy/Releases/Release-Process.html
> Distro: Jazzy Jalisco

---

## Overview

Each ROS 2 distribution goes through a development process spanning **more than a year**, beginning before the previous distribution's release. Target release: **World Turtle Day (May 23rd)**.

---

## Release Lifecycle Steps

| Step | Description |
|---|---|
| **Find the ROS Boss** | Person from Open Robotics internal team who shepherds the distribution through development, release, update, and EOL. |
| **Choose Distribution Name** | ROS Boss curates the naming process using community input and checking for conflicts. |
| **Create Documentation Page** | Lists vital statistics: planned release date, EOL date, significant changes since previous release. |
| **Set Release Timeline** | Plan the final weeks' deadlines (RMW freeze, distribution freeze, etc.). |
| **Produce Roadmap** | ROS Boss + ROS 2 dev team lead + TSC collaborate on achievable features and significant changes. |
| **Announce Roadmap** | Published via GitHub issue tracking progress on each roadmap item. Not fixed — welcomes new contributions. |
| **Set Target Platforms** | OS/distro/version + major dependencies (Python version, compiler, Eigen, etc.) fixed via REP-2000 update. |
| **Add Build Farm Support** | Add CI and binary package building for new target platforms if they differ from previous distro. |
| **Commission Logo** | Professional artist creates logo based on distribution name; turtlesim icon and other artwork produced. |
| **Create Mailing List** | For critical announcements (e.g. build farm failures for packages). |
| **Create Test Cases** | Integration test cases produced and provided to the release team for execution. |
| **Announce Upcoming RMW Freeze** | Warn devs that default RMW implementation will be feature-frozen soon. |
| **Upgrade Dependency Packages** | Update vendor packages to REP-2000 specified versions (especially important on Windows). |
| **Create Detailed Release Plan** | Plan final 2 months: test plan, timelines, dependencies between steps, assign people. |
| **Freeze RMW** | Default RMW implementation is feature-frozen for exhaustive testing. |
| **Announce Upcoming Overall Freeze** | Warn that core ROS packages will be feature-frozen next. |
| **Freeze Distribution** | No new features in core packages — only bug fixes. Rolling Ridley is temporarily frozen. |
| **Announce Upcoming Branch** | Prepare for branching new distribution from Rolling Ridley. |
| **Announce Upcoming Beta** | Wider community testing is about to begin. |
| **Branch from Rolling Ridley** | New distribution is born. Rolling Ridley unfreezes and resumes receiving new features. |
| **Add Distribution to CI** | CI updated to build against new distribution branches. |
| **Build Interim Testing Tarballs** | Build farm produces tarballs for testers. |
| **Add Distribution Documentation** | Detailed docs about significant changes added to docs site. |
| **Announce Beta** | Beta released — community invited to test broadly. More testers = more bugs found. |
| **Final Release Preparations** | Absolutely-everything-frozen phase. Binary packages built via build farm. |
| **Release** | Binary packages made available. Announcement made. Parties held. World Turtle Day 🐢 |

---

## Distributions Overview

### What is a Distribution?
A versioned set of ROS packages (like a Linux distro). Once released, changes limited to bug fixes and non-breaking improvements for core packages.

### Current Distributions (as of Jazzy)

| Distribution | Release Date | EOL |
|---|---|---|
| **Kilted Kaiju** | May 23, 2025 | December 2026 |
| **Jazzy Jalisco** | May 23, 2024 | **May 2029** (LTS) |
| **Humble Hawksbill** | May 23, 2022 | **May 2027** (LTS) |

### Future
| Distribution | Release Date | EOL |
|---|---|---|
| **Lyrical Luth** | May 2026 | May 2031 |

### Rolling Ridley
- Continuously updated rolling distribution (REP 2002, since June 2020).
- Serves as: (1) staging area for future stable distros, (2) collection of latest dev releases.
- Can have in-place breaking changes — not recommended for production.
- Packages released to Rolling are automatically released to future stable distros.

### Cross-Distribution Communication
- **NOT guaranteed** between distributions (e.g., Humble node ↔ Iron node).
- Cross-vendor single-distro communication is also NOT guaranteed.

---

## Key Dates & Cadence

- New distribution every year on **May 23rd** (World Turtle Day).
- **LTS distributions**: every other year, supported for 5 years.
- **Non-LTS distributions**: supported for ~1.5 years.
- **Rolling**: ongoing, no EOL.
