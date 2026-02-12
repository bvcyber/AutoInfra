import { useState } from "react";

const PasswordDisplay = ({ password }) => {
  const [isBlurred, setIsBlurred] = useState(true);

  const handleMouseEnter = () => setIsBlurred(false);
  const handleMouseLeave = () => setIsBlurred(true);
  const handleClick = () => setIsBlurred(!isBlurred);

  return (
    <span
      className={isBlurred ? "blur-sm transition-all duration-200" : "transition-all duration-200"}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {password}
    </span>
  );
};

export default PasswordDisplay;
