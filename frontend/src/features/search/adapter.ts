import type { CommandDescriptor } from "../../lib/commands";
import { commandDescription, commandExamples } from "./commands";
import { hitsToCommands } from "./ranking";
import type { SearchService } from "./service";
import type { SavedQuery, SearchResultHit } from "./types";

export interface SearchAdapterHandlers {
  runCommand: (text: string) => void | Promise<void>;
  runQuery: (query: string) => void | Promise<void>;
}

export function commandDescriptors(
  handlers: SearchAdapterHandlers,
  names: string[] = ["search", "find", "goto", "tag", "saved", "reindex"],
): CommandDescriptor[] {
  return names.map((name) => {
    const example = commandExamples(name)[0] ?? `/${name}`;
    return {
      id: `v2.command.${name}`,
      title: `/${name} — ${commandDescription(name)}`,
      group: "Search",
      keywords: [name, "search", "v2", ...commandExamples(name)],
      run: () => handlers.runCommand(example),
    };
  });
}

export function savedQueryDescriptors(
  saved: SavedQuery[],
  handlers: SearchAdapterHandlers,
): CommandDescriptor[] {
  return saved.map((item) => ({
    id: `v2.saved.${item.id}`,
    title: item.name,
    group: item.pinned ? "Pinned searches" : "Saved searches",
    keywords: [item.name, item.query, ...item.tags, "saved", "search"],
    run: () => handlers.runQuery(item.query),
  }));
}

export function hitCommandDescriptors(
  hits: SearchResultHit[],
  handlers: SearchAdapterHandlers,
): CommandDescriptor[] {
  return hitsToCommands(hits).map((command, index) => ({
    id: `v2.hit.${hits[index]?.node_id ?? index}`,
    title: `Open: ${hits[index]?.title ?? "result"}`,
    group: "Search results",
    keywords: [hits[index]?.title ?? "", command],
    run: () => handlers.runCommand(command),
  }));
}

export async function allSearchCommandDescriptors(
  service: SearchService,
  handlers: SearchAdapterHandlers,
): Promise<CommandDescriptor[]> {
  const definitions = await service.listCommands();
  const names = definitions
    .map((item) => String(item.name ?? item.id ?? ""))
    .filter(Boolean);
  const saved = await service.listSaved();
  return [
    ...commandDescriptors(handlers, names.length ? names : undefined),
    ...savedQueryDescriptors(saved, handlers),
  ];
}

export function mergeCommandDescriptors(
  ...groups: CommandDescriptor[][]
): CommandDescriptor[] {
  const byId = new Map<string, CommandDescriptor>();
  for (const group of groups) {
    for (const descriptor of group) byId.set(descriptor.id, descriptor);
  }
  return [...byId.values()];
}
