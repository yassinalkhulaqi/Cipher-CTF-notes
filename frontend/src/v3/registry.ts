/** Additive feature and command registries used by V3 branches. */

export interface V3Feature {
  id: string;
  label: string;
  route: string;
  order: number;
  capability?: string;
  icon?: string;
}

export interface V3Command {
  id: string;
  title: string;
  group: string;
  keywords: string[];
  run: () => void;
}

const features = new Map<string, V3Feature>();
const commands = new Map<string, V3Command>();

export function registerFeature(feature: V3Feature): void {
  features.set(feature.id, feature);
}

export function registerCommand(command: V3Command): void {
  commands.set(command.id, command);
}

export function listFeatures(): V3Feature[] {
  return Array.from(features.values()).sort(
    (a, b) => a.order - b.order || a.id.localeCompare(b.id),
  );
}

export function listCommands(): V3Command[] {
  return Array.from(commands.values()).sort(
    (a, b) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id),
  );
}

export function searchCommands(query: string): V3Command[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return listCommands();
  return listCommands().filter((command) => {
    const haystack = [command.title, command.group, ...command.keywords]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

export function findFeature(id: string): V3Feature | undefined {
  return features.get(id);
}

export function clearRegistries(): void {
  features.clear();
  commands.clear();
}

export function registrySnapshot(): {
  features: V3Feature[];
  commands: string[];
} {
  return {
    features: listFeatures(),
    commands: listCommands().map((command) => command.id),
  };
}
