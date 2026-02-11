import { useState } from "react";
import styles from "@/components/passwordDisplay.module.css";

const PasswordDisplay = ({ password }) => {
  const [isBlurred, setIsBlurred] = useState(true);

  const handleMouseEnter = () => setIsBlurred(false);
  const handleMouseLeave = () => setIsBlurred(true);
  const handleClick = () => setIsBlurred(!isBlurred);

  return (
    <span
      className={isBlurred ? styles.blurred : ""}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {password}
    </span>
  );
};

export default PasswordDisplay;
