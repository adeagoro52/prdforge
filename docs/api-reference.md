# PRDForge API Reference

This document provides a complete reference for the PRDForge REST API.

## Base URL

```
http://localhost:8000/api
```

## Authentication

Most endpoints require authentication via token. Include the token in requests:

```bash
# Query parameter
GET /api/users?token=your_token_here

# Or header (preferred)
Authorization: Bearer your_token_here
```

## Response Format

All responses are JSON. Successful responses return the requested data. Error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Endpoints

### Health

#### Check API Health
```http
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

---

### Projects

#### List All Projects
```http
GET /api/projects
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tags` | string | Comma-separated tags to filter by |
| `include_archived` | bool | Include archived projects (default: false) |

**Response:** `ProjectResponse[]`

#### Get Health Summary
```http
GET /api/projects/health-summary
```

Returns aggregated health status across all projects.

#### Get All Tags
```http
GET /api/projects/tags
```

Returns list of all unique tags used across projects.

#### List Archived Projects
```http
GET /api/projects/archived
```

**Response:** `ProjectResponse[]`

#### Create Project
```http
POST /api/projects
```

**Request Body:**
```json
{
  "name": "my-project",
  "path": "/path/to/project",
  "description": "Project description",
  "project_type": "local",
  "default_branch": "main",
  "tags": ["backend", "python"]
}
```

**Response:** `ProjectResponse` (201 Created)

#### Get Project
```http
GET /api/projects/{project_id}
```

**Response:** `ProjectResponse`

#### Update Project Tags
```http
PUT /api/projects/{project_id}/tags
```

**Request Body:**
```json
{
  "tags": ["frontend", "react"]
}
```

#### Archive Project
```http
POST /api/projects/{project_id}/archive
```

#### Unarchive Project
```http
POST /api/projects/{project_id}/unarchive
```

#### Delete Project
```http
DELETE /api/projects/{project_id}
```

---

### Runs

#### List Project Runs
```http
GET /api/projects/{project_id}/runs
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status (pending, running, paused, completed, failed) |
| `limit` | int | Max results (default: 50) |

**Response:** `RunResponse[]`

#### Create Run
```http
POST /api/projects/{project_id}/runs
```

**Request Body:**
```json
{
  "prd_path": "docs/prds/feature.json",
  "base_branch": "develop",
  "executor": "claude-cli"
}
```

**Response:** `RunResponse` (201 Created)

#### Get Run
```http
GET /api/runs/{run_id}
```

**Response:** `RunResponse`

#### Pause Run
```http
POST /api/runs/{run_id}/pause
```

#### Resume Run
```http
POST /api/runs/{run_id}/resume
```

#### Cancel Run
```http
POST /api/runs/{run_id}/cancel
```

---

### Skills

#### List All Skills
```http
GET /api/skills
```

**Response:** `SkillResponse[]`
```json
[
  {
    "name": "file-search",
    "description": "Search files by pattern or content",
    "version": "1.0.0",
    "type": "builtin",
    "enabled": true,
    "parameters": [...]
  }
]
```

#### Get Skill Details
```http
GET /api/skills/{skill_name}
```

**Response:** `SkillResponse`

---

### Executors

#### List All Executors
```http
GET /api/executors
```

**Response:** `ExecutorPluginResponse[]`
```json
[
  {
    "name": "claude-cli",
    "display_name": "Claude CLI",
    "description": "Execute tasks using Claude Code CLI",
    "version": "1.0.0",
    "capabilities": {
      "supports_streaming": true,
      "supports_context": true,
      "max_tokens": 8192
    },
    "status": "available",
    "requires_api_key": true,
    "api_key_configured": true
  }
]
```

#### Get Executor Details
```http
GET /api/executors/{executor_name}
```

#### Check Executor Health
```http
GET /api/executors/{executor_name}/health
```

**Response:**
```json
{
  "name": "claude-cli",
  "healthy": true,
  "latency_ms": 245,
  "last_check": "2024-01-15T10:30:00Z",
  "error": null
}
```

#### Check All Executors Health
```http
GET /api/executors/health/all
```

#### Test Executor
```http
POST /api/executors/{executor_name}/test
```

Runs a simple test task to verify executor functionality.

---

### Cost Tracking

#### Create Cost Record
```http
POST /api/projects/{project_id}/costs
```

**Request Body:**
```json
{
  "run_id": "run-abc123",
  "task_id": "task-001",
  "executor_name": "claude-api",
  "model": "claude-sonnet-4-20250514",
  "input_tokens": 1500,
  "output_tokens": 800,
  "total_cost": 0.0115
}
```

#### List Cost Records
```http
GET /api/projects/{project_id}/costs
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `run_id` | string | Filter by run |
| `start_date` | date | Filter from date |
| `end_date` | date | Filter to date |
| `limit` | int | Max results |

#### Get Cost Summary
```http
GET /api/projects/{project_id}/costs/summary
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | day, week, month (default: month) |

**Response:**
```json
{
  "total_cost": 45.67,
  "total_input_tokens": 125000,
  "total_output_tokens": 85000,
  "by_model": {
    "claude-sonnet-4-20250514": {"cost": 30.00, "calls": 150},
    "gpt-4": {"cost": 15.67, "calls": 50}
  }
}
```

#### Get Run Costs
```http
GET /api/runs/{run_id}/costs
```

#### Get/Set Budget
```http
GET /api/projects/{project_id}/budget
PUT /api/projects/{project_id}/budget
DELETE /api/projects/{project_id}/budget
```

**PUT Request Body:**
```json
{
  "monthly_limit": 100.00,
  "alert_threshold": 0.8,
  "hard_limit": true
}
```

#### Get Budget Status
```http
GET /api/projects/{project_id}/budget/status
```

**Response:**
```json
{
  "budget": 100.00,
  "spent": 45.67,
  "remaining": 54.33,
  "percentage_used": 45.67,
  "alert_triggered": false,
  "hard_limit_reached": false
}
```

#### Get Cost Alerts
```http
GET /api/projects/{project_id}/alerts
```

#### Acknowledge Alert
```http
POST /api/alerts/{alert_id}/acknowledge
POST /api/projects/{project_id}/alerts/acknowledge-all
```

#### Global Cost Summary
```http
GET /api/costs/summary
```

#### Estimate Cost
```http
GET /api/costs/estimate
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name |
| `input_tokens` | int | Estimated input tokens |
| `output_tokens` | int | Estimated output tokens |

---

### Git Branches

#### List Branches
```http
GET /api/projects/{project_id}/branches
```

#### Get Branch Graph
```http
GET /api/projects/{project_id}/branches/graph
```

Returns visual branch structure for graph rendering.

#### Get Branch Commits
```http
GET /api/projects/{project_id}/branches/{branch_name}/commits
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max commits (default: 50) |

#### Compare Branches
```http
GET /api/projects/{project_id}/branches/compare
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `base` | string | Base branch |
| `head` | string | Head branch |

---

### Quality Gates

#### List Built-in Gates
```http
GET /api/quality-gates/builtin
```

**Response:**
```json
[
  {
    "name": "lint",
    "display_name": "Linting",
    "description": "Run code linter",
    "commands": {
      "python": "ruff check .",
      "javascript": "eslint .",
      "typescript": "eslint . --ext .ts,.tsx"
    }
  }
]
```

#### Detect Project Gates
```http
GET /api/projects/{project_id}/quality-gates/detect
```

Auto-detects available quality gates based on project type.

#### Run All Gates
```http
POST /api/projects/{project_id}/quality-gates/run
```

**Response:**
```json
{
  "passed": true,
  "total": 3,
  "passed_count": 3,
  "failed_count": 0,
  "results": [
    {"name": "lint", "passed": true, "output": "..."},
    {"name": "test", "passed": true, "output": "..."},
    {"name": "build", "passed": true, "output": "..."}
  ]
}
```

#### Run Specific Gate
```http
POST /api/projects/{project_id}/quality-gates/check/{gate_name}
```

#### Add Custom Gate
```http
POST /api/projects/{project_id}/quality-gates/custom
```

**Request Body:**
```json
{
  "name": "security-scan",
  "command": "npm audit --audit-level=high",
  "timeout_seconds": 300,
  "required": true
}
```

---

### Authentication

#### Login
```http
POST /api/auth/login
```

**Request Body:**
```json
{
  "username": "admin",
  "password": "password",
  "remember_me": false
}
```

**Response:**
```json
{
  "token": "abc123...",
  "expires_at": "2024-01-15T22:00:00Z",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

#### Logout
```http
POST /api/auth/logout?token=...
```

#### Get Current User
```http
GET /api/auth/me?token=...
```

#### Extend Session
```http
POST /api/auth/extend?token=...
```

---

### Users

#### Create User
```http
POST /api/users
```

**Request Body:**
```json
{
  "username": "newuser",
  "email": "user@example.com",
  "password": "securepassword",
  "display_name": "New User",
  "role": "member"
}
```

#### List Users
```http
GET /api/users
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `role` | string | Filter by role |
| `active` | bool | Filter by active status |

#### Get User
```http
GET /api/users/{user_id}
```

#### Update User
```http
PUT /api/users/{user_id}
```

#### Change Password
```http
POST /api/users/{user_id}/password
```

**Request Body:**
```json
{
  "current_password": "oldpass",
  "new_password": "newpass"
}
```

#### Reset Password (Admin)
```http
POST /api/users/{user_id}/reset-password
```

#### Get/Update User Settings
```http
GET /api/users/{user_id}/settings
PUT /api/users/{user_id}/settings
```

#### Delete User
```http
DELETE /api/users/{user_id}
```

---

### Notifications

#### Get Notification Config
```http
GET /api/projects/{project_id}/notifications/config
```

#### Update Notification Config
```http
PUT /api/projects/{project_id}/notifications/config
```

**Request Body:**
```json
{
  "events": ["run_completed", "run_failed", "task_failed"],
  "channels": ["in_app", "webhook"],
  "webhook_url": "https://hooks.slack.com/...",
  "webhook_secret": "optional_secret"
}
```

#### Delete Notification Config
```http
DELETE /api/projects/{project_id}/notifications/config
```

#### List Notifications
```http
GET /api/notifications
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `unread_only` | bool | Only unread notifications |
| `project_id` | int | Filter by project |
| `limit` | int | Max results |

#### Get Unread Count
```http
GET /api/notifications/count
```

**Response:**
```json
{
  "unread_count": 5
}
```

#### Mark as Read
```http
POST /api/notifications/{notification_id}/read
```

#### Mark All as Read
```http
POST /api/notifications/read-all
```

#### Delete Notification
```http
DELETE /api/notifications/{notification_id}
```

#### Get Webhook Deliveries
```http
GET /api/projects/{project_id}/webhooks
```

#### Get Webhook Stats
```http
GET /api/projects/{project_id}/webhooks/stats
```

**Response:**
```json
{
  "total_deliveries": 150,
  "successful": 145,
  "failed": 5,
  "average_latency_ms": 234,
  "success_rate": 96.67
}
```

#### List Event Types
```http
GET /api/notifications/event-types
```

**Response:**
```json
[
  "run_started",
  "run_completed",
  "run_failed",
  "task_started",
  "task_completed",
  "task_failed",
  "budget_warning",
  "quality_gate_failed"
]
```

#### List Channels
```http
GET /api/notifications/channels
```

**Response:**
```json
["in_app", "webhook", "email", "slack"]
```

---

### Audit Logs

#### List Audit Logs
```http
GET /api/audit-logs
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | int | Filter by user |
| `action` | string | Filter by action type |
| `start_date` | date | Filter from date |
| `end_date` | date | Filter to date |
| `limit` | int | Max results |

---

## Data Types

### ProjectResponse
```json
{
  "id": 1,
  "name": "my-project",
  "path": "/path/to/project",
  "description": "Description",
  "project_type": "local",
  "default_branch": "main",
  "tags": ["backend"],
  "health": "healthy",
  "is_archived": false,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T12:00:00Z"
}
```

### RunResponse
```json
{
  "id": 1,
  "run_id": "run-abc123",
  "project_id": 1,
  "prd_path": "docs/prds/feature.json",
  "base_branch": "develop",
  "run_branch": "prdforge/feature-abc123",
  "status": "running",
  "total_tasks": 10,
  "completed_tasks": 5,
  "failed_tasks": 0,
  "current_task": "backend-003",
  "executor": "claude-cli",
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": null
}
```

### NotificationResponse
```json
{
  "id": 1,
  "event_type": "run_completed",
  "title": "Run Completed",
  "message": "Run abc123 completed successfully",
  "priority": "normal",
  "is_read": false,
  "action_url": "/runs/abc123",
  "project_id": 1,
  "run_id": "abc123",
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

## Error Codes

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid or missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Resource already exists |
| 422 | Validation Error - Invalid request body |
| 500 | Internal Server Error |

---

## Rate Limiting

Currently no rate limiting is enforced. For production deployments, consider adding a reverse proxy with rate limiting.

## Webhooks

Webhook payloads are signed with HMAC-SHA256. Verify the signature using the `X-PRDForge-Signature` header:

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```
