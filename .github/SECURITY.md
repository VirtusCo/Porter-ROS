# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| Latest  | Yes                |
| Older   | No                 |

Only the latest release receives security updates. Users are expected to stay on the current version.

## Reporting a Vulnerability

Do NOT report security vulnerabilities through public GitHub issues.

Instead, send an email to **virtusco.tech@gmail.com** with the following information:

- Description of the vulnerability.
- Steps to reproduce the issue.
- Affected components (ROS 2 package, ESP32 firmware, AI assistant, etc.).
- Potential impact and severity assessment.
- Any suggested fix, if available.

## Response Timeline

- **Acknowledgment**: within 48 hours of receipt.
- **Initial assessment**: within 5 business days.
- **Resolution or mitigation**: timeline communicated after assessment, based on severity.

## What Qualifies as a Security Issue

- Remote code execution in any ROS 2 node or firmware component.
- Unauthorized access to robot control interfaces (motor commands, navigation).
- Bypass of safety mechanisms (watchdog, emergency stop, obstacle avoidance).
- Data exfiltration from the on-device AI assistant or passenger interactions.
- Denial-of-service attacks against safety-critical subsystems.
- Supply chain vulnerabilities in direct dependencies.

## Scope Exclusions

- Vulnerabilities requiring physical access to the robot hardware.
- Issues in third-party dependencies that should be reported upstream.
- Bugs that do not have a security impact.

Thank you for helping keep Porter Robot and its users safe.
