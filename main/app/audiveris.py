import subprocess
import logging
from pathlib import Path
from typing import Optional, Union
from time import sleep

logger = logging.getLogger(__name__)

class AudiverisConverter:
    def __init__(self, audiveris_path: str = "/app/audiveris/build/install/audiveris/bin/audiveris"):
        self.audiveris_path = Path(audiveris_path)
        self._validate_installation()
        
    def _validate_installation(self):
        if not self.audiveris_path.exists():
            raise FileNotFoundError(
                f"Audiveris not fount at {self.audiveris_path}. Verify docker installation contains Audiveris."
                )
            
    def convert_to_musicxml(
        self,
        input_path: str,
        output_dir: str,
        timeout: int = 1800
    ) -> Optional[str]:
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        
        try:
            cmd = [
                str(self.audiveris_path),
                "-batch",
                "-export",
                "-save",
                "-print",
                "-constant", "omr.fallback.Reader=PDF_BOX", 
                "-constant", "org.audiveris.omr.sheet.BookManager.useOpus=true",
                
                "-constant", "ocr.engine=TesseractOCR",
                "-constant", "ocr.language=eng",
                "-constant", "ocr.tessdataPath=/usr/share/tessdata",
                "-constant", "ocr.legacyMode=true",
                "-constant", "ocr.engineMode=0",
                "-constant", "omr.engine.tesseract.path=/usr/bin/tesseract", 
                "-constant", "omr.engine.tesseract.dataPath=/usr/share/tessdata",
                
                "-constant", "omr.steps.RHYTHMS.maxRetries=5",
                "-constant", "omr.rhythms.preserveOriginalVoices=true",
                "-constant", "omr.rhythms.maxDuration=16",
                "-constant", "omr.steps.RHYTHMS.maxGap=6",  
                "-constant", "omr.steps.TIME.maxCandidates=2",
                "-constant", "omr.steps.KEYS.maxCandidates=2",
                "-constant", "omr.steps.CLEFS.maxCandidates=2",
                "-constant", "omr.steps.RHYTHMS.useSamples=true", 
                "-constant", "omr.steps.GRID.staffLineThickness=3", 
                "-constant", "omr.steps.GRID.minStaffLineCount=4",
                "-constant", "omr.steps.GRID.peakMergeX=0.5",
                "-constant", "omr.steps.GRID.peakMergeY=0.3", 
                "-constant", "omr.steps.TIME_PURITY=0.9", 
                "-constant", "omr.steps.BEAMS.maxSlope=0.3",
                "-constant", "omr.steps.BEAMS.minGrade=0.3"
                "-constant", "omr.steps.BEAMS.maxThickness=4"
                "-constant", "omr.steps.HEADS.minGrade=0.5",
                "-constant", "omr.steps.STEMMING.minStemLength=8",  # Reduce if stems are short (default=10)
                "-constant", "omr.steps.STEMMING.minStemWidth=1",   # Reduce for thinner stems (default=2)
                "-constant", "omr.steps.STEMMING.peakThreshold=20", # Lower to detect faint stems (default=30) 
                "-constant", "sheet.maxStubs=5",
                "-constant", "sheet.maxErrors=100",
                "-constant", "omr.sheet.staves.allowTablature=false",
                "-constant", "book.export.force=true",              # Force export even on partial success 
                
                "-output", str(output_dir),
                str(input_path)
            ]
            
            logger.debug(f"Running command {' '.join(cmd )}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            
            sleep(10 if input_path.stat().st_size > 1_000_000 else 5) 
            
                
            mxl_file = output_dir / f"{input_path.stem}.opus.mxl"
            
            if mxl_file.exists():
                logger.info(f"Successfully generated {mxl_file}")
                return str(mxl_file)
            
            else:
                logger.error(f"MXL file missing. Directory contents:")
                for f in output_dir.glob("*"):
                    logger.error(f" - {f}")
                return None            
        
        except subprocess.TimeoutExpired:
            logger.error(f"Conversion timed out after {timeout}s")
            return None
        except subprocess.CalledProcessError as e:
            logger.error("Audiveris crash details:")
            logger.error(f"Command: {e.cmd}")
            logger.error(f"Exit code:  {e.returncode}")
            logger.error(f"STDOUT:\n{e.stdout[:2000]}")
            logger.error(f"STDERR:\n{e.stderr[:2000]}")
            return None