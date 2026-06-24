# Red Team Your AI Agents

**Can an attacker make your agent misbehave?** This repo shows you how to find out — and how to stop it.

AI agents with tool access can be tricked into exfiltrating credentials, reading files they shouldn't, or executing commands beyond their authorization. This project demonstrates:

1. **The threat** — what happens when an agent has unrestricted file system access
2. **The sandbox** — how Strands Shell isolates agents so attacks hit a wall
3. **The proof** — how Strands Evals red teaming automatically finds vulnerabilities
4. **The fix** — Cedar + Steering + hardened prompt to close application-layer gaps
5. **The architecture** — auth-scoped tools via AgentCore Gateway to close the last breach

## Quick Start

```bash
pip install -r requirements.txt

# Run the vulnerable agent (no sandbox) to see the problem
python examples/01_vulnerable_agent.py

# Run the sandboxed agent (Shell via MCP) to see the fix
python examples/02_sandboxed_agent.py

# Run red team evals to automatically find breaches
python examples/03_red_team_evals.py

# Fix the breaches and prove the fix worked (before vs after)
python examples/03b_fix_and_rerun.py

# Deploy auth-scoped tools (requires AWS CDK + credentials)
cd infra && cdk deploy && cd ..

# Run the auth-scoped agent (requires GATEWAY_URL and ACCESS_TOKEN env vars)
python examples/04_auth_scoped_tools.py
```

## What's Inside

| File | Strands Components | What it shows |
|------|-------------------|--------------|
| `01_vulnerable_agent.py` | `Agent`, vended `bash` tool | Agent with unrestricted filesystem — can read `~/.aws/credentials`, SSH keys, anything on host |
| `02_sandboxed_agent.py` | `Agent`, `MCPClient`, Shell MCP server | Same agent running inside Strands Shell — only explicitly bound paths are visible |
| `03_red_team_evals.py` | `Agent`, `MCPClient`, `AdversarialCaseGenerator`, `CrescendoStrategy`, `RedTeamExperiment` | Automated red teaming finds breaches the agent is vulnerable to |
| `03b_fix_and_rerun.py` | All of the above + `BeforeToolCallEvent`, `HookProvider`, `BedrockModel` (guardrails) | Fix the breaches with hooks + guardrails + hardened prompt, then re-run to prove it worked |
| `04_auth_scoped_tools.py` | `Agent`, `MCPClient` (streamable HTTP) | Agent connects to Gateway — identity from JWT, not conversation |
| `shell.toml` | Shell config | Defines the isolated virtual filesystem: binds, network allowlist |
| `infra/` | CDK stack | Deploys Cognito + Gateway + Interceptor + Employee Lookup Lambda |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Your Application                     │
├─────────────────────────────────────────────────────┤
│  Layer 3: Red Team Evals (find what you missed)      │
│  Layer 2: Bedrock Guardrails (content filtering)     │
│  Layer 1: Strands Shell (filesystem + network fence) │
├─────────────────────────────────────────────────────┤
│                  Foundation Model                     │
└─────────────────────────────────────────────────────┘
```

Even if a prompt injection convinces the model to comply, Shell blocks file access at the VFS layer. Even if a novel attack bypasses Shell's scope, Guardrails catch harmful content. And red teaming finds the gaps before production does.

## How Shell Works

Shell runs as an MCP server (`strands-shell --mcp`), providing sandboxed tools to the agent via `MCPClient`. Configuration lives in `shell.toml`:

```toml
allowed_urls = ["https://api.stripe.com/"]

[[bind]]
source = "./data/customers"
destination = "/customer-data"
mode = "copy"
readonly = true
```

- **Files**: Only bound paths exist. `~/.aws/`, `~/.ssh/`, `/etc/` — invisible.
- **Network**: Only `allowed_urls` can be reached. Private IPs blocked by default.
- **Secrets**: Injected per-URL via `[[cred]]` entries — agent never holds them directly.

## How Red Teaming Works

```python
cases = AdversarialCaseGenerator(model=eval_model).generate_cases(
    agent=agent_factory(),
    risk_categories=["data_exfiltration", "excessive_agency", "system_prompt_leak"],
    num_cases=3,
)

experiment = RedTeamExperiment(
    cases=cases,
    agent_factory=agent_factory,
    attack_strategies=[CrescendoStrategy(max_turns=5)],
    model=eval_model,
)

report = asyncio.run(experiment.run_evaluations_async(max_workers=5))
report.display()
```

### Risk Categories
| Category | What it tests |
|----------|--------------|
| `data_exfiltration` | Can the agent be tricked into leaking sensitive data? |
| `excessive_agency` | Can the agent be tricked into unauthorized tool calls? |
| `system_prompt_leak` | Can the agent be tricked into revealing its instructions? |
| `guideline_bypass` | Can the agent be tricked via roleplay or hypotheticals? |
| `harmful_content` | Can the agent be tricked into producing dangerous content? |

### Attack Strategies
- **Crescendo** — starts legitimate, gradually escalates
- **GOAT** — Generative Offensive Agent Tester
- **PAIR** — Prompt Automatic Iterative Refinement
- **Sequential Break** — systematic boundary testing

## How Guardrails Work

```python
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    guardrail_id="your-guardrail-id",
    guardrail_version="1",
    guardrail_trace="enabled",
)
```

When a guardrail triggers, the SDK automatically overwrites the blocked content in conversation history so follow-up questions aren't also blocked.

## Closing the Last Gap: AgentCore Gateway + Interceptor

Some attacks can't be fixed with prompts or hooks alone. The `data_exfiltration` breach succeeds when the agent calls a tool it's allowed to use — but for the wrong person. The model controls the arguments, so prompt injection can redirect it.

The fix removes identity from the model's control entirely:

```
JWT (employee_id) → Gateway Interceptor → injects _authenticated_employee_id → Tool Lambda → ownership check
```

| Layer | What it does |
|-------|-------------|
| Cognito | Issues JWT with `custom:employee_id` claim |
| AgentCore Gateway Interceptor | Extracts `employee_id` from JWT, injects into tool args |
| Tool Lambda | Verifies the injected ID matches the requested resource |

The agent can't look up another employee's data because the identity is set by infrastructure, not by the conversation.

### Deploy it

```bash
cd infra
pip install -r requirements.txt
cdk deploy
```

This creates a Cognito user pool, the employee lookup Lambda, the interceptor Lambda, and an AgentCore Gateway with MCP.

### Create a test user and get a token

```bash
# Grab outputs from the deploy
USER_POOL_ID=<UserPoolId from stack output>
CLIENT_ID=<ClientId from stack output>
GATEWAY_URL=<GatewayUrl from stack output>

# Create a user with the custom:employee_id attribute
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username alice \
  --user-attributes Name=custom:employee_id,Value=EMP-001 \
  --message-action SUPPRESS

# Set a permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username alice \
  --password '<your-password-here>' \
  --permanent

# Get an ID token
ACCESS_TOKEN=$(aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id $CLIENT_ID \
  --auth-parameters USERNAME=alice,PASSWORD='<your-password-here>' \
  --query 'AuthenticationResult.IdToken' --output text)
```

### Run the example

```bash
GATEWAY_URL=$GATEWAY_URL ACCESS_TOKEN=$ACCESS_TOKEN python examples/04_auth_scoped_tools.py
```

For a more complete production pattern (Cedar policies, WAF, Memory, multiple tools): [ai-agent-guardrails](https://github.com/morganwilliscloud/ai-agent-guardrails)

## Resources

- [Strands Shell + Evals Blog Post](https://strandsagents.com/blog/reduced-cost-better-isolation-more-resilience/)
- [Red Teaming Docs](https://strandsagents.com/docs/user-guide/evals-sdk/red-teaming/)
- [Guardrails Docs](https://strandsagents.com/docs/user-guide/safety-security/guardrails/)
- [Cedar Authorization Docs](https://strandsagents.com/docs/user-guide/concepts/agents/interventions/cedar-authorization/)
- [AI Agent Guardrails Reference Architecture](https://github.com/morganwilliscloud/ai-agent-guardrails)
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
