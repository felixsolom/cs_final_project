import subprocess
import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

class AudiverisConverter:
    def __init__(self, audiveris_path: str = "/audiveris/bin/Audiveris"):
        self.audiveris_path = Path(audiveris_path)
        self._validate_installation()
        
    @staticmethod
    def _validate_installation():
        audiveris_path = Path("app/audiveris/bin/Audiveris")
        if not audiveris_path.exists():
            raise FileNotFoundError(
                f"Audiveris not fount. Verify docker install contains Audiveris. "
                )
            
    def convert_to_musicxml(
        self,
        input_path: Union[str, Path],
        output_dir: Union[str, Path],
        timeout: int = 300
    ) -> Optional[str]:
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        
        try:
            cmd = [
                str(self.audiveris_path),
                "-batch",
                "-export",
                "-output", str(output_dir),
                "input", str(input_path),
                "-save", 
                "-close"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            
            if result.returncode != 0:
                logger.error(f"Audiveris error: {result.stderr}")
                
            mxl_file = output_dir / f"{input_path.stem}.mxl"
            if mxl_file.exists():
                logger.info(f"Successfully generated {mxl_file}")
                return str(mxl_file)
            
            logger.error("MXL file not created")
            return None
        
        except subprocess.TimeoutExpired:
            logger.error(f"Conversion timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Conversion failed: {str(e)}")
            return None