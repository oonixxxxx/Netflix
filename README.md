# Netflix Dispatch - Incident Management Platform

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Build Status](https://github.com/Netflix/dispatch/workflows/CI/badge.svg)](https://github.com/Netflix/dispatch/actions)
[![Documentation Status](https://readthedocs.org/projects/dispatch/badge/?version=latest)](https://netflix.github.io/dispatch/)

Netflix Dispatch is an open-source incident management platform designed to streamline coordination during critical events.

## Table of Contents
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)
- [License](#license)

## Features

🚀 **Core Capabilities**:
- End-to-end incident management
- Real-time collaboration
- Customizable workflows
- Comprehensive audit logging

🔌 **Integrations**:
- Slack, Microsoft Teams
- Jira, PagerDuty
- AWS, GCP, Kubernetes
- Custom webhook support

📊 **Analytics**:
- MTTR tracking
- Incident trends
- Post-mortem automation

## Quick Start

### Using Docker
```bash
git clone https://github.com/Netflix/dispatch.git
cd dispatch
docker-compose up
```

Access the web interface at http://localhost:8000

## Installation

### Requirements
- Python 3.8+
- PostgreSQL 12+
- Redis

### Steps
1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up database:
   ```bash
   createdb dispatch
   alembic upgrade head
   ```
4. Run the server:
   ```bash
   uvicorn dispatch.main:app --reload
   ```

## Configuration

Configure Dispatch via `.env` file:

```ini
DATABASE_URL=postgresql://user:password@localhost/dispatch
SECRET_KEY=your-secret-key-here
SLACK_API_TOKEN=xoxb-your-token
```

See [configuration docs](https://netflix.github.io/dispatch/configuration/) for all options.

## API Documentation

Dispatch provides a RESTful API for integration:

```bash
# List incidents
curl -X GET "http://localhost:8000/api/v1/incidents" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Full API documentation available at [API Docs](https://netflix.github.io/dispatch/api/).

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.
