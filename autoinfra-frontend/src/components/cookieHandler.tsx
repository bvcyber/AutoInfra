export const GetCookie = (cookieToGet: string): string => {
  try {
    if (typeof window !== "undefined") {
      const cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (document.cookie.indexOf(cookieToGet) === -1) {
          return "false";
        } else {
          if (cookie.startsWith(`${cookieToGet}=`)) {
            return cookie.substring(cookieToGet.length + 1);
          }
        }
      }
    } else {
      return "Cannot get window.";
    }
  } catch (e) {
    return `Error getting cookie: ${e}`;
  }
  return "cookie stuff";
};

export const SetCookie = (cookieToSet: string, cookieValue: string) => {
  try {
    if (typeof window !== "undefined") {
      document.cookie = `${cookieToSet}=${cookieValue}`;
    } else {
      return "Cannot get window.";
    }
  } catch (e) {
    return `Error setting cookie: ${e}`;
  }
};

export const DeleteCookie = (cookieToDelete: string) => {
  try {
    if (typeof window !== "undefined") {
      document.cookie = `${cookieToDelete}=;expires=Thu, 01 Jan 1970 00:00:01 GMT`;
    } else {
      return "Cannot get window.";
    }
  } catch (e) {
    return `Error deleting cookie: ${e}`;
  }
};
