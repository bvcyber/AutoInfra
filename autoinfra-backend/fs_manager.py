from typing import Dict, Any
import json
import os
import logging

logger = logging.getLogger("backend-logs")

def load_file(fileTypeDirectory: str, fileName: str) -> Dict[str, Any]:
    if fileName != "false":
        try:
            with open(os.path.join(fileTypeDirectory, fileName),'r') as fd:
                logger.info(f"LOAD_FILE: Successfully loaded file: {fileName}")
                return json.loads(fd.read())
        except:
            logger.error(f"LOAD_FILE: Unable to load file {fileName}. File not found.")
            return {"ERROR":"File not found"}
    else:
        logger.info(f"LOAD_FILE: No deployment to load")
        return {"ERROR":"File not found"}

def save_file(saveData, fileTypeDirectory, fileName):
    try:
        with open(os.path.join(fileTypeDirectory, fileName),'w') as fd:
            fd.write(json.dumps(saveData))
            logger.info(f"SAVE_FILE: Successfully saved file: {fileName}")
    except:
        logger.error(f"SAVE_FILE: Unable to save file {fileName}. File not found.")
        return {"ERROR":"File not found"}

def delete_file(fileTypeDirectory, fileName):
    try:
        if fileName != ".gitkeep":
            os.remove(os.path.join(fileTypeDirectory, fileName))
            logger.info(f"DELETE_FILE: Successfully deleted file: {fileName}")
    except:
        logger.error(f"DELETE_FILE: Unable to delete file {fileName}. File not found.")
        return {"ERROR":"File not found"}
