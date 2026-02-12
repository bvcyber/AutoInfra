"use client"
import React from "react"
import {
  Disclosure,
  DisclosureButton,
  DisclosurePanel,
} from "@headlessui/react"

const faqItems = [
  {
    question: "What is AutoInfra?",
    answer:
      "Auto Infra, a convenient way for users to deploy and host infrastructure (predominantly AD environments) in a user friendly interface. This will serve as a centralized location for engineers internally to learn AD/Azure, host infrastructure for projects and workshops, and much more.",
  },
  {
    question: "Where should I start?",
    answer:
      "Depends on your use case? You want to learn on prem AD? Go to deploy. Want to host an AD environment for a project or research for attacks? Go to deploy.",
  },
  {
    question: "How do I deploy a scenario?",
    answer:
      "Click Deploy on the navbar to the left. Choose the desired scenario (Either a network AD scenario or a docker scenario). The info and config at the right indicates the information for the desired scenario. Click Submit.",
    videoSrc: "/video/deploy.mp4",
  },
  {
    question: "I have a scenario up and running, what now?",
    answer:
      "Go to environment on the navbar to the left to take you to the current active environment. At 'Info and Config', there are different options to configure the environment, either adding users, enabling individual attacks or enabling full-blown ctfs. For the scenarios 'SMALL', 'FULL','DCONLY', and 'ACDS', there are no users, so be sure to make users first before enabling individual attacks.",
    videoSrc: "/video/Enable_user_attack.mp4",
  },
  {
    question:
      "I want to actually connect to the scenario now. How do I do this?",
    answer:
      "If you chose a network scenario, the jumpbox connection details will be available to you. Utilize your favorite rdp tool to connect. Additionally, to connect to the windows machines, you must first connect to jumpbox(public ip) in order to then connect to windows machine. Utilize your preffered rdp tool (e.g remmina pre-installed). If docker scenario, simply copy connection details and paste them onto new browser tab.",
    videoSrc: "/video/Connect_to_network_or_docker_scenario.mp4",
  },
  {
    question: "How do I save my current environment?",
    answer:
      "Click Environment on the left navbar to take you to your current environment and click Save. Make note of your Deployment ID to re-deploy later. Please note, this process takes some time. Refrain from loading the environment until the destruction process has started. You can monitor the progress in the Deployed Environments section.",
    imgSrc: "/save.png",
  },
  {
    question: "My environment is done saving, how do I re-deploy it?",
    answer:
      "Once your environment is in the Destroying phase, click Load Deployment on the left, select your deployment from the drop-down, and click Deploy.",
  },
  // Add more FAQs as needed
]

export default function Page() {
  return (
    <div className="pl-5 pr-5 w-[100%] min-w-[20rem] flex flex-col max-h-[55rem] overflow-y-auto">
      <div className="text-base-content text-2xl font-extrabold text-left">
        FAQ
      </div>
      <br />
      {faqItems.map((item, index) => (
        <Disclosure key={index}>
          {({ open }) => (
            <>
              <DisclosureButton className="">
                <div className="label border-4 border-double border-base-300 w-[100%]">
                  <span className="text-base-content text-lg font-extrabold">
                    {item.question}
                  </span>
                  <span>{open ? "−" : "+"}</span>
                </div>
              </DisclosureButton>
              <DisclosurePanel className="pt-4 pb-2 text-base-content">
                <p>{item.answer}</p>
                {item.imgSrc && (
                  <div className="relative w-full overflow-hidden mt-2">
                    <img src={item.imgSrc}></img>
                  </div>
                )}
                {item.videoSrc && (
                  <div className="relative w-full overflow-hidden mt-2">
                    <video
                      controls
                      autoPlay
                      loop
                      className="w-full max-w-full rounded-lg"
                    >
                      <source src={item.videoSrc} type="video/mp4" />
                      Your browser does not support the video tag.
                    </video>
                  </div>
                )}
              </DisclosurePanel>
            </>
          )}
        </Disclosure>
      ))}
    </div>
  )
}