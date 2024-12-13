from pathlib import Path
from typing import List, Dict
import os
import textwrap

class ModuleGenerator:
    def __init__(self, base_path: str = "app"):
        self.base_path = Path(base_path)
        self.modules = {
            "profile": {
                "relationships": [("User", "one_to_one")],
                "fields": [
                    ("avatar_url", "String"),
                    ("bio", "String"),
                    ("location", "String"),
                    ("website", "String"),
                    ("created_at", "DateTime"),
                    ("updated_at", "DateTime")
                ]
            },
            "follow": {
                "relationships": [("User", "many_to_many")],
                "fields": [
                    ("follower_id", "Integer"),
                    ("following_id", "Integer"),
                    ("created_at", "DateTime"),
                    ("status", "String")
                ]
            },
            "settings": {
                "relationships": [("User", "one_to_one")],
                "fields": [
                    ("notification_preferences", "JSON"),
                    ("privacy_settings", "JSON"),
                    ("theme", "String"),
                    ("language", "String"),
                    ("timezone", "String"),
                    ("updated_at", "DateTime")
                ]
            }
        }

    def generate_model(self, module_name: str) -> str:
        module_config = self.modules[module_name]
        class_name = f"{module_name.title()}"
        
        relationship_code = self._generate_relationships(module_config["relationships"], module_name)
        
        return textwrap.dedent(f'''
            from datetime import datetime
            from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
            from sqlalchemy.orm import relationship
            from app.db.base import Base
            from app.auth.models import User

            class {class_name}(Base):
                __tablename__ = "{module_name}s"
                
                id = Column(Integer, primary_key=True)
                user_id = Column(Integer, ForeignKey("users.id"), unique={module_config["relationships"][0][1] == "one_to_one"})
                
                # Fields
                {self._generate_fields(module_config["fields"])}
                
                # Relationships
                {relationship_code}
                
                def __repr__(self):
                    return f"<{class_name}(id=self.id, user_id=self.user_id)>"
        ''')

    def generate_schema(self, module_name: str) -> str:
        class_name = f"{module_name.title()}"
        return textwrap.dedent(f'''
            from datetime import datetime
            from typing import Optional
            from pydantic import BaseModel

            class {class_name}Base(BaseModel):
                {self._generate_schema_fields(self.modules[module_name]["fields"])}

                class Config:
                    from_attributes = True

            class {class_name}Create(BaseModel):
                {self._generate_schema_fields(self.modules[module_name]["fields"], optional=False)}

            class {class_name}Update(BaseModel):
                {self._generate_schema_fields(self.modules[module_name]["fields"], optional=True)}
        ''')

    def generate_router(self, module_name: str) -> str:
        class_name = f"{module_name.title()}"
        return textwrap.dedent(f'''
            from fastapi import APIRouter, Depends, HTTPException
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.auth.dependencies import current_active_user
            from app.db.base import get_async_session
            from app.auth.models import User
            from . import service
            from .schemas import {class_name}Create, {class_name}Update

            router = APIRouter(prefix="/{module_name}", tags=["{module_name}"])

            @router.get("/me")
            async def get_my_{module_name}(
                user: User = Depends(current_active_user),
                session: AsyncSession = Depends(get_async_session)
            ):
                {module_name} = await service.get_{module_name}_by_user_id(session, user.id)
                if not {module_name}:
                    raise HTTPException(status_code=404, detail=f"{class_name} not found")
                return {module_name}

            @router.put("/me")
            async def update_my_{module_name}(
                data: {class_name}Update,
                user: User = Depends(current_active_user),
                session: AsyncSession = Depends(get_async_session)
            ):
                updated_{module_name} = await service.update_{module_name}(session, user.id, data)
                if not updated_{module_name}:
                    raise HTTPException(status_code=404, detail=f"{class_name} not found")
                return updated_{module_name}
        ''')

    def generate_service(self, module_name: str) -> str:
        class_name = f"{module_name.title()}"
        return textwrap.dedent(f'''
            from sqlalchemy.ext.asyncio import AsyncSession
            from sqlalchemy import select
            from .models import {class_name}
            from .schemas import {class_name}Create, {class_name}Update

            async def get_{module_name}_by_user_id(session: AsyncSession, user_id: int):
                result = await session.execute(
                    select({class_name}).where({class_name}.user_id == user_id)
                )
                return result.scalar_one_or_none()

            async def update_{module_name}(
                session: AsyncSession, 
                user_id: int, 
                data: {class_name}Update
            ):
                {module_name}_db = await get_{module_name}_by_user_id(session, user_id)
                if not {module_name}_db:
                    {module_name}_db = {class_name}(user_id=user_id)
                    session.add({module_name}_db)
                
                for key, value in data.dict(exclude_unset=True).items():
                    setattr({module_name}_db, key, value)
                
                await session.commit()
                await session.refresh({module_name}_db)
                return {module_name}_db
        ''')

    def _generate_fields(self, fields: List[tuple]) -> str:
        return "\n    ".join(
            f"{name} = Column({type})" for name, type in fields
        )

    def _generate_schema_fields(self, fields: List[tuple], optional: bool = False) -> str:
        type_mapping = {
            "String": "str",
            "Integer": "int",
            "DateTime": "datetime",
            "JSON": "dict"
        }
        return "\n    ".join(
            f"{name}: {'Optional[' if optional else ''}{type_mapping[type]}{']' if optional else ''}" 
            for name, type in fields
        )

    def _generate_relationships(self, relationships: List[tuple], module_name: str) -> str:
        rel_strings = []
        for model, rel_type in relationships:
            if rel_type == "one_to_one":
                rel_strings.append(f'{model.lower()} = relationship("{model}", back_populates="{module_name.lower()}")')
            elif rel_type == "many_to_many":
                association_table_name = f"{model.lower()}_{module_name.lower()}_association"
                rel_strings.append(f'users = relationship("{model}", secondary="{association_table_name}", back_populates="{module_name.lower()}")')
        return "\n    ".join(rel_strings)

    def generate_all(self):
        for module_name in self.modules:
            module_path = self.base_path / module_name
            module_path.mkdir(parents=True, exist_ok=True)
            
            # Create __init__.py
            (module_path / "__init__.py").touch()
            
            # Create each module file
            files = {
                "models.py": self.generate_model,
                "schemas.py": self.generate_schema,
                "router.py": self.generate_router,
                "service.py": self.generate_service
            }
            
            for filename, generator in files.items():
                with open(module_path / filename, "w") as f:
                    f.write(generator(module_name))

if __name__ == "__main__":
    generator = ModuleGenerator()
    generator.generate_all()