"use client";

import EnvironmentInfo from "./EnvironmentInfo";
import InfoAndConfig from "@/components/infoAndConfig";

export default function Page() {
  const pageLocation = "HOME";
  return (
    <div className="flex flex-col xl:flex-row gap-6">
      <div className="flex-1 xl:max-w-[30rem]">
        <EnvironmentInfo />
      </div>
      <div className="flex-1">
        <InfoAndConfig
          incomingSelectedScenarioFromParent={""}
          pageLocation={pageLocation}
        />
      </div>
    </div>
  );
}
