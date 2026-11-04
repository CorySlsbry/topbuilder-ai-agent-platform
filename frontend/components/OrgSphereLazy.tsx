"use client";

// Loads the WebGL sphere only when the 3D view is actually shown, keeping three/R3F out of the
// initial dashboard bundle. ssr:false because WebGL cannot server-render.

import dynamic from "next/dynamic";

import { Spinner } from "@/components/ui";

const OrgSphere = dynamic(() => import("./OrgSphere"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full w-full place-items-center text-zinc-500">
      <Spinner />
      <span className="mt-3 text-sm">Loading 3D sphere…</span>
    </div>
  ),
});

export default OrgSphere;
