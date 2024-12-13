from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path

class BaseTemplate(ABC):
    """Base class for all template generators"""
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.output_path: Optional[Path] = None
    
    @abstractmethod
    def generate_model(self) -> str:
        """Generate model template"""
        pass
    
    @abstractmethod
    def generate_relationships(self) -> str:
        """Generate relationship definitions"""
        pass
    
    @abstractmethod
    def generate_init(self) -> str:
        """Generate __init__.py content"""
        pass
    
    def set_output_path(self, path: str) -> None:
        """Set output path for generated files"""
        self.output_path = Path(path)
    
    def write_to_file(self, content: str, filename: str) -> None:
        """Write generated content to file"""
        if not self.output_path:
            raise ValueError("Output path not set")
            
        file_path = self.output_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            f.write(content)
            
    def generate(self) -> Dict[str, str]:
        """Generate all templates for the module"""
        return {
            'model': self.generate_model(),
            'relationships': self.generate_relationships(),
            'init': self.generate_init()
        }