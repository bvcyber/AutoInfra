import Link from "next/link"

const navLinks = [
  { name: "Environment", location: "/" },
  { name: "Build", location: "/build" },
  { name: "Deploy", location: "/deploy" },
  { name: "BloodHound", location: "/bloodhound" },
  { name: "Azure Setup", location: "/azureSetup" },
]

export default function SideNav() {
  return (
    <div className="nav-container">
      {navLinks.map((item, index) => (
        <Link key={index} href={item.location} className="nav-link">
          {item.name}
        </Link>
      ))}
    </div>
  )
}
