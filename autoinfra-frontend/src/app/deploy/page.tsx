"use client";
import DeployForm from "./DeployForm";
import Deploying from "@/components/deploying";
import InfoAndConfig from "@/components/infoAndConfig";
import Loading from "@/components/loading";
import { FetchEnvironmentState } from "@/components/fetchEnvironmentState";
import { useEffect, useState } from "react";

export default function Page() {
  const [envState, setEnvState] = useState<string | null>(null); // null = loading
  const [selectedScenario, setSelectedScenario] = useState("");
  const [isDeploying, setIsDeploying] = useState(false); // Track local deploying state
  const pageLocation = "DEPLOY";

  useEffect(() => {
    const FetchEnvironmentStateEffect = async () => {
      try {
        const envData = await FetchEnvironmentState();
        setEnvState(envData || "No deployment");
        // If already deploying from a previous session, set local state
        if (envData === "deploying") {
          setIsDeploying(true);
        }
      } catch (error) {
        console.error("Error fetching environment state:", error);
        setEnvState("No deployment");
      }
    };
    FetchEnvironmentStateEffect();
  }, []);

  // Callback when deployment is initiated
  const onDeploymentStarted = () => {
    setIsDeploying(true);
  };

  // Show loading while checking environment state
  if (envState === null) {
    return <Loading />;
  }

  // Show Deploying screen if we're deploying (either from server state or local trigger)
  if (envState === "deploying" || isDeploying) {
    return <Deploying customMessage="Deploying scenario..." />;
  }

  // Show the deploy page for all other cases
  return (
    <div className="flex flex-col xl:flex-row gap-6">
      <div className="flex-1 xl:max-w-[30rem]">
        <DeployForm setValue={setSelectedScenario} onDeploymentStarted={onDeploymentStarted} />
      </div>
      <div className="flex-1">
        <InfoAndConfig
          incomingSelectedScenarioFromParent={selectedScenario}
          pageLocation={pageLocation}
        />
      </div>
    </div>
  );
}