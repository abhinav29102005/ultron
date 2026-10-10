export async function onRequest(): Promise<Response> {
  const data = {
    status: "ok",
    description: "ULTRON Cloud LLM & API Key Hub",
    providers: [
      {
        id: "nvidia",
        name: "NVIDIA NIM",
        badge: "1,000 Free Credits",
        portalUrl: "https://build.nvidia.com/",
        freeTier: "1,000 Free API credits on signup (No credit card needed)",
        recommendedModels: "nvidia/nemotron-3-super-120b-a12b, meta/llama-3.3-70b-instruct",
        cliCommand: "ultron /key nvidia nvapi-..."
      },
      {
        id: "groq",
        name: "Groq Cloud",
        badge: "Free Tier (500+ tok/s)",
        portalUrl: "https://console.groq.com/keys",
        freeTier: "Fastest LPU inference with generous free rate limits",
        recommendedModels: "openai/gpt-oss-120b, openai/gpt-oss-20b",
        cliCommand: "ultron /key groq gsk_..."
      },
      {
        id: "openrouter",
        name: "OpenRouter",
        badge: "100+ Models Aggregator",
        portalUrl: "https://openrouter.ai/keys",
        freeTier: "Unified API gateway for Claude 3.5, DeepSeek, and Llama",
        recommendedModels: "deepseek/deepseek-chat, anthropic/claude-3.5-sonnet",
        cliCommand: "ultron /key openrouter sk-or-..."
      },
      {
        id: "openai",
        name: "OpenAI Platform",
        badge: "GPT-4o & Embeddings",
        portalUrl: "https://platform.openai.com/api-keys",
        freeTier: "Direct platform access for GPT-4o and text-embedding-3",
        recommendedModels: "gpt-4o, text-embedding-3-small",
        cliCommand: "ultron /key openai sk-..."
      },
      {
        id: "anthropic",
        name: "Anthropic Claude",
        badge: "Claude 3.5 Sonnet",
        portalUrl: "https://console.anthropic.com/",
        freeTier: "Anthropic console access for Claude 3.5 Sonnet and Haiku",
        recommendedModels: "claude-3-5-sonnet-20241022",
        cliCommand: "ultron /key anthropic sk-ant-..."
      },
      {
        id: "ollama",
        name: "Local Ollama",
        badge: "100% Offline · Zero Keys",
        portalUrl: "https://ollama.com/",
        freeTier: "Completely private, local CPU/GPU execution with zero telemetry",
        recommendedModels: "qwen2.5:7b-instruct, llama3.2:3b",
        cliCommand: "ultron /mode offline"
      }
    ],
    cliCommands: {
      interactiveWizard: "/setup",
      portalHub: "/hub",
      setKey: "/key <provider> <api_key>",
      toggleOffline: "/mode offline"
    }
  };

  return new Response(JSON.stringify(data, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=300"
    }
  });
}
