import GlobalConfigs from "../app/app.config";
import { SetCookie } from "./cookieHandler";

export const CheckAuth = async () => {
  const response = await fetch(GlobalConfigs.checkAuthEndpoint);
  const data = await response.json();
  return data.message;
};

export const AzureAuth = async () => {
  const response = await fetch(GlobalConfigs.azureAuthEndpoint);
  const data = await response.json();
  if (data === "Authorized") {
    SetCookie("azureAuth", "true");
  }
  return data.message;
};
