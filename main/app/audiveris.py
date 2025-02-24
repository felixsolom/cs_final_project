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
                "-option", "org.audiveris.omr.sheet.BookManager.useOpus=true",
                "-option", "org.audiveris.omr.text.Language.defaultSpecification=eng+ita",
                "-option", "org.audiveris.omr.text.tesseract.path=/usr/local/bin/tesseract",
                "-option", "org.audiveris.omr.text.tesseract.datadir=/usr/local/share/tessdata",
                "-option", "org.audiveris.omr.text.tesseract.ocrEngineMode=1",  # LSTM mode
                "-option", "org.audiveris.omr.batch.threadCount=4",  # Parallel processing
                "-option", "org.audiveris.omr.batch.memoryMax=4096", # 4GB heap
                
                "-option", "org.audiveris.omr.sheet.SheetStub.maxErrors=500",  
                "-option", "org.audiveris.omr.steps.sheet.MaxStubs=20",  
                "-option", "book.export.force=true",  

                "-option", "org.audiveris.omr.steps.TEXTS.minGrade=0.05",  
                "-option", "org.audiveris.omr.steps.DYNAMICS.minGrade=0.15",  
                "-option", "org.audiveris.omr.steps.SYMBOLS.minGrade=0.1",
                
                "-option", "omr.sheet.staves.voidPartCreation=true",  # Keeps irregular staff regions  
                "-option", "omr.sheet.parts.mergePolicy=ALWAYS",      # Forces system connectivity  
                "-option", "omr.steps.GRID.peakMergeX=1.0",           # Broad horizontal staff merging  
                "-option", "omr.steps.GRID.peakMergeY=0.8",           # Loose vertical staff alignment  

                # Removing TIME processing  
                "-option", "omr.steps.TIME.maxCandidates=0",  
                # Disabling key signature analysis  
                "-option", "omr.steps.KEYS.maxCandidates=0",  
                # Bypassing clef validation  
                "-option", "omr.steps.CLEFS.maxCandidates=0", 
                
                "-option", "musicxml.extension.visualDescriptors=true", # Shape complexity metrics  

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