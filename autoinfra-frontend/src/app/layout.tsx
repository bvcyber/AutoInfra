import type { Metadata } from "next";
import "./globals.css";
import SideNav from "@/components/sideNav";
import DeployedEnvironments from "@/components/deployedEnvironments";
import AzureStatus from "@/components/azureStatus";
import { DeploymentProvider } from "@/contexts/DeploymentContext";
import { AuthProvider } from "@/contexts/AuthContext";

export const metadata: Metadata = {
  title: {
    default: "Auto Infra",
    template: "%s | Auto Infra",
  },
  description: "Auto Infra",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen w-full overflow-x-auto">
        <AuthProvider>
          <DeploymentProvider>
            <div className="flex flex-row gap-x-3 px-3 pt-4 pb-4 min-h-screen">
          <div className="flex flex-col gap-y-3 flex-shrink-0">
            <div className="flex justify-center card-container w-fit min-w-[9.8rem]">
              <img
                src="/logo.png"
                alt="Logo"
                className="h-[8rem] w-auto pt-1 pb-1"
              />
            </div>
            <AzureStatus />
            <div className="card-container w-fit min-w-[10rem] h-fit">
              <SideNav />
            </div>
          </div>
          <div className="flex-grow card-container pt-[3rem] px-[5rem] pb-[3rem] min-w-0 overflow-auto">
            {children}
          </div>
          <div className="flex flex-none w-[22rem] flex-shrink-0">
            <div className="card-container px-2 py-2 divide-y divide-solid w-full h-fit max-h-[calc(100vh-2rem)] overflow-y-auto">
              <div>
                <h1 className="darker-text-color font-extrabold leading-none tracking-tight lg:text-md lg:mx-auto lg:px-10 lg:py-3 rounded-lg text-center">
                  Deployed Environments
                </h1>
              </div>
              <div>
                <div className="darker-text-color font-extrabold leading-none tracking-tight lg:text-xl lg:mx-auto">
                  <DeployedEnvironments />
                </div>
              </div>
            </div>
          </div>
            </div>
          </DeploymentProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
