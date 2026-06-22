import pytest
from a2a_registry.models import AgentCard, AgentCapabilities, AgentInterface, AgentSkill


@pytest.fixture
def sample_card() -> AgentCard:
    """A2A v0.3 agent card — top-level url field."""
    return AgentCard(
        name="Test Agent",
        description="A test agent",
        url="http://agent.example.com",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        skills=[AgentSkill(id="greet", name="Greeter")],
    )


@pytest.fixture
def sample_card_v1() -> AgentCard:
    """A2A v1.0 agent card — url inside supportedInterfaces."""
    return AgentCard(
        name="Test Agent v1",
        description="A v1.0 test agent",
        supportedInterfaces=[
            AgentInterface(
                url="http://agent-v1.example.com/jsonrpc",
                protocolBinding="json-rpc/2.0",
                protocolVersion="1.0",
            )
        ],
        version="2.0.0",
        capabilities=AgentCapabilities(streaming=True),
        skills=[AgentSkill(id="greet", name="Greeter")],
    )
