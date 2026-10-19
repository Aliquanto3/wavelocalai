// Module « Documents » : ses écrans et leur état (voir `core/registry.js`).

export const documentsModule = {
  id: "documents",
  icon: "description",
  screens: [
    {
      id: "documents-chat",
      path: "/documents",
      status: "available",
      load: () => import("../../screens/documents.js"),
    },
    {
      id: "documents-base",
      path: "/documents/base",
      status: "available",
      load: () => import("../../screens/documents-base.js"),
    },
    {
      id: "documents-evaluation",
      path: "/documents/evaluation",
      param: "run_id",
      status: "planned",
    },
  ],
};
