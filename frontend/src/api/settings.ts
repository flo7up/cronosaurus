import type { AppSettings } from "../types/chat";

const BASE = "/api/settings";

export async function fetchSettings(): Promise<AppSettings> {
  const res = await fetch(BASE);
  if (!res.ok) throw new Error("Failed to fetch settings");
  return res.json();
}

export async function updateSettings(data: Partial<AppSettings>): Promise<AppSettings> {
  const res = await fetch(BASE, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update settings");
  return res.json();
}

export async function getOnboardingStatus(): Promise<{ completed: boolean }> {
  const res = await fetch(`${BASE}/onboarding`);
  if (!res.ok) throw new Error("Failed to fetch onboarding status");
  return res.json();
}

export async function completeOnboarding(data: {
  project_endpoint: string;
  model_deployment_name?: string;
  available_models?: string[];
  cosmos_url?: string;
  cosmos_key?: string;
  cosmos_db?: string;
  google_search_api_key?: string;
  google_search_engine_id?: string;
  configure_email?: boolean;
  configure_cosmos?: boolean;
}): Promise<AppSettings> {
  const res = await fetch(`${BASE}/onboarding/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to complete onboarding");
  return res.json();
}

export interface FoundryDeployment {
  name: string;
  model_name: string;
  model_publisher: string;
  model_version: string;
}

export async function fetchDeployments(): Promise<{ success: boolean; deployments: FoundryDeployment[]; error?: string }> {
  const res = await fetch(`${BASE}/deployments`);
  if (!res.ok) throw new Error("Failed to fetch deployments");
  return res.json();
}

export async function fetchProviderModels(): Promise<{ success: boolean; models: { id: string; owned_by: string }[]; error?: string }> {
  const res = await fetch(`${BASE}/provider-models`);
  if (!res.ok) throw new Error("Failed to fetch provider models");
  return res.json();
}

export async function testFoundryConnection(): Promise<{ success: boolean; error?: string; message?: string }> {
  const res = await fetch(`${BASE}/test-foundry`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to test Foundry connection");
  return res.json();
}

export async function testCosmosConnection(): Promise<{ success: boolean; error?: string; message?: string }> {
  const res = await fetch(`${BASE}/test-cosmos`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to test Cosmos connection");
  return res.json();
}
