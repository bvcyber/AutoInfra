import { GetCookie } from "./cookieHandler";
import GlobalConfigs from "../app/app.config";

export const FetchEnvironmentState = async () => {
  const deploymentID = GetCookie("deploymentID");
  
  if (deploymentID !== "error" && deploymentID && deploymentID !== "false") {
    // Move this declaration outside the try block so it's available in the catch block
    const isBuildDeployment = deploymentID.startsWith("BuildLab-");
    
    try {
      // For build deployments, check if we just started THIS SPECIFIC build
      if (isBuildDeployment) {
        const buildStartTime = localStorage.getItem("buildStartTime");
        const buildStartDeploymentID = localStorage.getItem("buildStartDeploymentID");

        if (buildStartTime && buildStartDeploymentID === deploymentID) {
          const timeSinceBuild = Date.now() - parseInt(buildStartTime);
          // If less than 10 minutes since THIS build started, assume it's still deploying
          if (timeSinceBuild < 10 * 60 * 1000) {
            return "deploying";
          }
        }
      }
      
      // Standard request - we're now sending properly formatted JSON
      const response = await fetch(GlobalConfigs.getDeploymentStateEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          deploymentID
        }),
        cache: "no-cache",
      });
      
      if (!response.ok) {
        console.error("Failed to fetch environment state, status:", response.status);
        if (isBuildDeployment) {
          // For build deployments, be more lenient with errors
          return "deploying";
        }
        return null;
      }
      
      const data = await response.json();
      
      // If the message indicates file not found for a build deployment
      if (data.message === "File not found" || data.message === "Could not load deployment") {
        if (isBuildDeployment) {
          return "deploying";
        }
        return null;
      }
      
      return data.message;
    } catch (error) {
      console.error("Error in FetchEnvironmentState:", error);
      // For build deployments, be more lenient with errors
      if (isBuildDeployment) return "deploying";
      return null;
    }
  } else {
    return null;
  }
};