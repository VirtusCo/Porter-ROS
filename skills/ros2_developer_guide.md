# ROS 2 Developer Guide — Skill File

> Source: https://docs.ros.org/en/jazzy/The-ROS2-Project/Contributing/Developer-Guide.html
> Distro: Jazzy Jalisco

---

## General Principles

- **Shared ownership**: No one "owns" code — everyone is free to propose changes anywhere, handle any ticket, review any PR.
- **Be willing to work on anything**: All devs should contribute to any aspect of the system.
- **Ask for help**: Use tickets, comments, or email when stuck.

---

## Quality Practices

### Versioning (SemVer + ROS Rules)

- Follow **Semantic Versioning** (`semver.org`).
- **Major** version increments (breaking changes) should NOT happen within a released ROS distribution.
- Patch and minor increments are allowed within a release.
- Multiple breaking changes should be merged into the integration branch (e.g. `rolling`) but released together.
- A new distribution does NOT necessarily require a major bump.
- For compiled code, **ABI is part of the public interface** — recompile-required changes are major (breaking).
- ABI breaking changes CAN happen in minor bumps BEFORE a distribution release.
- API stability is enforced even for `0.x.x` packages (since Dashing/Eloquent).

#### Public API Declaration

- Every package must clearly declare its public API (in quality declaration).
- C/C++: typically any installed header is public API.
- Python: must be explicitly declared.
- Build artifacts (CMake config, executables, CLI options) can also be public API.

#### Deprecation Strategy (Tick-Tock)

| Distribution | State |
|---|---|
| X-turtle | `void foo();` |
| Y-turtle | `[[deprecated("use bar()")]] void foo(); void bar();` |
| Z-turtle | `void bar();` |

- No deprecations after a distribution is released.
- Deprecation can be introduced in minor bump before release.

### Change Control Process

- **All changes must go through a pull request.**
- **DCO required** on ROSCore repos: all commits need `Signed-off-by:` line (`git commit -s`).
- DCO not required for trivial changes (whitespace, typos).
- Always run CI for all **Tier 1 platforms** for every PR, include links.
- **Minimum 1 approval** from a non-author developer before merging.
- Documentation changes must be proposed before merging related code.

#### Backporting Guidelines

- Merge into `rolling` first, then backport to older supported distros.
- Title backport PRs: `[Distro] <name of original PR>`.
- Link to all original PRs in the backport description.
- Mergify can automate backports.

### Documentation Requirements

Every package README (or linked docs) must have:
- Description and purpose
- Public API definition and description
- Examples
- Build and install instructions
- Test instructions
- Documentation build instructions
- Developer workflow (e.g. `python setup.py develop`)
- License and copyright statements

Each source file must have a license/copyright statement (checked by linter).
Each package must have a LICENSE file (typically Apache 2.0).

### Testing

- **Unit tests**: in the package being tested; use Mock; no non-tool test deps.
- **Integration tests**: in the package; test software interfaces as users would; minimize external test deps.
- **System tests**: in their own packages to avoid coupling/circular deps.
- **Code coverage**: ≥95% line coverage target. Justify lower if needed.
- **Performance tests**: strongly recommended; check before each release.
- **Linters**: use `ament_lint_common` (all linters required). See `ament_lint_auto` for setup.

---

## General Practices

### Issues

Include in every issue:
- OS and version
- Installation method (debs, binary, source)
- Specific ROS 2 version
- DDS/RMW implementation
- Client library in use
- Steps to reproduce (SSCCE preferred)
- Troubleshooting already tried

### Branches

- Separate branch per distribution (e.g. `humble`, `jazzy`).
- Releases made from distribution branches.
- `main` typically targets Rolling.
- Maintainers must backport/forwardport as appropriate.

### Pull Requests

- One change per PR.
- Minimal patch size, no unnecessary changes.
- Minimum number of meaningful commits.
- Don't squash during review; squash before merge.
- Use draft PRs for work-in-progress.
- Link dependent PRs with `- Depends on <link>`.
- Reviewers can make minor improvements in-place.
- Allow edits from upstream contributors on fork PRs.
- Use "Squash and Merge" when merging.
- Delete branch after merge.

### Library Versioning

- All libraries within a package share the same version.
- If libraries need different versions, split into different packages.

### Development Process

- Default branch must always build, pass tests, compile without warnings.
- Always build with tests enabled.
- Always run tests locally before proposing PR.
- Run CI for all platforms for every PR.

### Package Naming (REP-144)

- Lower case, start with letter, underscore separators: e.g. `laser_viewer`.
- Be specific: `wavefront_planner` not `planner`.
- Avoid catchall names like `utils`.
- Prefix only for non-general packages (e.g. `pr2_`).
- Don't prefix with `ros`.

### Units and Coordinates

- Follow **REP-0103** for units and coordinate conventions.
- Follow **REP-0117** for special distance conditions ("too close", "too far").

### Programming Conventions

- **Defensive programming**: check every return code, throw on unhandled cases.
- All error messages to `stderr`.
- Declare variables in narrowest scope.
- Keep groups (deps, imports, includes) alphabetically ordered.
- **C++ specific**:
  - Avoid `<<` streaming to stdout/stderr (thread interleaving risk).
  - Avoid references for `std::shared_ptr` (subverts reference counting).

### Filesystem Layout

#### Package Layout

| Directory | Contents |
|---|---|
| `src/` | C/C++ code + non-installed headers |
| `include/<pkg>/` | Installed C/C++ headers (namespace by package) |
| `<package_name>/` | Python code |
| `test/` | Tests and test data |
| `config/` | YAML params, RViz configs |
| `doc/` | Documentation |
| `launch/` | Launch files |
| `msg/` | Message definitions |
| `srv/` | Service definitions |
| `action/` | Action definitions |
| `package.xml` | REP-0140 package manifest |
| `CMakeLists.txt` | CMake packages only |
| `setup.py` | Python-only packages |
| `README` | Landing page |
| `CONTRIBUTING` | Contribution guidelines |
| `LICENSE` | License file |
| `CHANGELOG.rst` | REP-0132 changelog |

#### Repository Layout

- Each package in a subfolder matching the package name.
- Single-package repos can optionally be at root.

---

## Developer Workflow

1. Discuss design (GitHub issue + design PR to `ros2/design` if needed)
2. Write implementation on feature branch on a fork
3. Write tests
4. Enable and run linters
5. Run tests locally: `colcon test`
6. Run CI on feature branch (ci.ros2.org → `ci_launcher`)
7. Post CI job links on PR
8. When approved → "Squash and Merge"
9. Delete branch

### Gitconfig Optimization

```ini
[url "ssh://git@github.com/"]
  insteadOf = https://github.com/
```

---

## Software Development Lifecycle (SDLC)

1. **Task Creation** — issue in appropriate ros2 repo with clear success criteria
2. **Design Document** — contribute to `ros2/design` for new features; not required for bug fixes
3. **Design Review** — assign package owners as reviewers; optional design meeting for complex changes
4. **Implementation** — self-review with `git add -i`; signed commits (`git commit -s`); reference related issues
5. **Code Review** — open PR per modified repo; iterate on feedback; package maintainers merge

---

## Build Farm (ci.ros2.org)

### Job Categories

| Type | Jobs |
|---|---|
| **Manual** | `ci_linux`, `ci_linux-aarch64`, `ci_linux_coverage`, `ci_linux-rhel`, `ci_windows`, `ci_launcher` |
| **Nightly Debug** | `nightly_linux_debug`, `nightly_linux-aarch64_debug`, `nightly_linux-rhel_debug`, `nightly_win_deb` |
| **Nightly Release** | `nightly_linux_release`, `nightly_linux-aarch64_release`, `nightly_linux-rhel_release`, `nightly_win_rel` |
| **Nightly Repeated** | `nightly_linux_repeated`, `nightly_linux-aarch64_repeated`, `nightly_linux-rhel_repeated`, `nightly_win_rep` |
| **Coverage** | `nightly_linux_coverage` |
| **Packaging** | `packaging_linux`, `packaging_linux-rhel`, `packaging_windows` |

### Local Coverage with lcov

```bash
# Install
sudo apt install -y lcov

# Build with coverage flags
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_FLAGS="${CMAKE_CXX_FLAGS} --coverage" \
  -DCMAKE_C_FLAGS="${CMAKE_C_FLAGS} --coverage"

# Baseline
lcov --no-external --capture --initial --directory . --output-file ~/ros2_base.info

# Run tests
colcon test --packages-select <pkg> <test_pkg>

# Capture
lcov --no-external --capture --directory . --output-file ~/ros2.info

# Combine
lcov --add-tracefile ~/ros2_base.info --add-tracefile ~/ros2.info --output-file ~/ros2_coverage.info

# Generate HTML
mkdir -p coverage && genhtml ~/ros2_coverage.info --output-directory coverage
```
