import yaml

with open('routing-matrix.yaml', 'r') as f:
    data = yaml.safe_load(f)

new_routes = [
    {
        "id": "docs_to_search",
        "from": "documentation",
        "to": "web_search",
        "data_flow": "TEXT → TEXT",
        "protocol": "MCP → MCP",
        "automatable": True,
        "exemplars": [{"source": "read_docs", "target": "search_web"}]
    },
    {
        "id": "search_to_analysis",
        "from": "web_search",
        "to": "code_analysis_mcp",
        "data_flow": "TEXT → JSON",
        "protocol": "MCP → MCP",
        "automatable": True,
        "exemplars": [{"source": "tavily_search", "target": "analyze_code"}]
    },
    {
        "id": "academic_to_apps",
        "from": "academic_research",
        "to": "knowledge_apps",
        "data_flow": "TEXT → TEXT",
        "protocol": "MCP → MCP",
        "automatable": True,
        "exemplars": [{"source": "semanticSearch", "target": "notion-create-pages"}]
    },
    {
        "id": "editor_to_browser",
        "from": "claude_code_core",
        "to": "browser_playwright",
        "data_flow": "CODE → TEXT",
        "protocol": "FILESYSTEM → MCP",
        "automatable": True,
        "exemplars": [{"source": "Write", "target": "navigate"}]
    },
    {
        "id": "browser_to_github",
        "from": "browser_playwright",
        "to": "github_platform",
        "data_flow": "TEXT → JSON",
        "protocol": "MCP → MCP",
        "automatable": True,
        "exemplars": [{"source": "evaluate", "target": "create_pull_request"}]
    },
    {
        "id": "analysis_to_testing",
        "from": "code_analysis_mcp",
        "to": "test_runner_cli",
        "data_flow": "JSON → TEXT",
        "protocol": "MCP → CLI",
        "automatable": True,
        "exemplars": [{"source": "analyze", "target": "pytest"}]
    }
]

data['routes'].extend(new_routes)

# Sort routes by id to keep it clean (optional)

with open('routing-matrix.yaml', 'w') as f:
    yaml.dump(data, f, sort_keys=False, default_flow_style=False)

with open('ontology.yaml', 'r') as f:
    ont = yaml.safe_load(f)

# Add capability weights to some clusters
for cluster in ont.get('clusters', []):
    if cluster['id'] == 'web_search':
        cluster['capability_weights'] = {'SEARCH': 1.0, 'READ': 0.3}
    if cluster['id'] == 'knowledge_graph':
        cluster['capability_weights'] = {'STORE': 1.0, 'ORGANIZE': 0.8}
    if cluster['id'] == 'claude_code_core':
        cluster['capability_weights'] = {'WRITE': 1.0, 'READ': 0.8, 'EXECUTE': 0.5}

# Add relationships
ont['relationships'] = [
    {
        "source": "perplexity_research",
        "target": "knowledge_graph",
        "type": "FEEDS"
    },
    {
        "source": "tavily_search",
        "target": "web_search",
        "type": "ALTERNATIVE_TO"
    },
    {
        "source": "claude_code_core",
        "target": "git_core",
        "type": "INVOKES"
    },
    {
        "source": "git_core",
        "target": "github_platform",
        "type": "BRIDGES"
    },
    {
        "source": "code_analysis_mcp",
        "target": "claude_code_core",
        "type": "ENHANCES"
    }
]

with open('ontology.yaml', 'w') as f:
    yaml.dump(ont, f, sort_keys=False, default_flow_style=False)

print("Added routes and relationships")
