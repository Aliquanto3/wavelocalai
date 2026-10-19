// Module « Agents » : ses écrans et leur état (voir `core/registry.js`).

export const agentsModule = {
  id: "agents",
  icon: "smart-toy",
  screens: [
    {
      id: "agents-solo",
      path: "/agents/seul",
      status: "available",
      load: () => import("../../screens/agents-solo.js"),
    },
    { id: "agents-crew", path: "/agents/equipe", param: "run_id", status: "planned" },
  ],
};
