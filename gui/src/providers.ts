export type ProviderFramework = {
  id: string
  native_name?: string
  backbone?: string
  action_head?: string
  fusion?: string
}

export type ProviderDescriptor = {
  name: string
  spec: { adapter_version: string; capabilities: string[] }
  capabilities: {
    jobs?: string[]
    frameworks?: ProviderFramework[]
    execution_modes?: string[]
    native_config_passthrough?: boolean
  }
  default_environment: string
}

export type ProviderDoctor = {
  provider: string
  environment: string
  ready: boolean
  checks: Record<string, { ok: boolean; required: boolean; value?: unknown }>
}

export function buildProviderDoctorPath(
  provider: string,
  environment?: string,
  providerRoot?: string,
): string {
  const query = new URLSearchParams()
  if (environment) query.set('environment', environment)
  if (providerRoot) query.set('provider_root', providerRoot)
  const suffix = query.toString()
  return `/providers/${encodeURIComponent(provider)}/doctor${suffix ? `?${suffix}` : ''}`
}

export function providerArchitectureRows(provider: ProviderDescriptor) {
  return (provider.capabilities.frameworks ?? []).map(item => ({
    framework: item.native_name ? `${item.id} / ${item.native_name}` : item.id,
    backbone: item.backbone ?? '—',
    actionHead: item.action_head ?? '—',
    fusion: item.fusion ?? '—',
  }))
}
