/** Additive registration with the V3 feature/command registries. */

import { registerCommand, registerFeature } from "../../v3/registry";

let installed = false;

export function registerAutomation(): void {
  if (installed) return;
  installed = true;
  registerFeature({
    id: "automation",
    label: "Playbook automation",
    route: "/automation",
    order: 60,
    capability: "automation",
    icon: "workflow",
  });
  registerCommand({
    id: "automation.focus",
    title: "Focus playbook automation",
    group: "Automation",
    keywords: ["playbook", "dag", "dry run", "automation"],
    run: () => {
      const element = document.querySelector<HTMLElement>('[data-automation="feature"]');
      element?.focus?.();
      element?.scrollIntoView?.({ block: "start" });
    },
  });
  registerCommand({
    id: "automation.dry-run-hint",
    title: "Automation: dry runs never write",
    group: "Automation",
    keywords: ["trace", "safe", "inspect"],
    run: () => undefined,
  });
}

export function automationInstalled(): boolean {
  return installed;
}
