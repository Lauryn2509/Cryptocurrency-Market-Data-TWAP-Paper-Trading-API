import importlib
import sys
import pkg_resources
from packaging import version

def check_dependencies():
    """
    Verify if all dependencies needed to run the GUI, server, etc. are available. 
    """
    required_packages = {
        # Client
        "requests": "2.25.0",
        "websockets": "10.0",
        "asyncio": "3.4.3",
        
        # Server
        "fastapi": "0.68.0",
        "uvicorn": "0.15.0",
        "httpx": "0.22.0",
        "slowapi": "0.1.4",
        "passlib": "1.7.4",
        
        # GUI 
        "PyQt5": "5.15.0",  
        
        # Others
        "pydantic": "1.8.0",
        "pytest": "6.2.0",
    }
    
    all_packages_installed = True
    missing_packages = []
    outdated_packages = []
    
    print("\n=== Dependencies check ===\n")
    
    for package_name, min_version in required_packages.items():
        try:
            # We try to import the package
            pkg = importlib.import_module(package_name)
            
            # Get installed version
            try:
                pkg_version = pkg_resources.get_distribution(package_name).version
                installed_version = version.parse(pkg_version)
                required_version = version.parse(min_version)
                
                if installed_version >= required_version:
                    print(f"{package_name} - version {pkg_version} (required: {min_version}) installed !")
                else:
                    print(f"{package_name} - version {pkg_version} installed, but {min_version} ou more recent needed")
                    outdated_packages.append(f"{package_name} (current : {pkg_version}, required : {min_version})")
                    all_packages_installed = False
            except:
                # Specific case for asyncio which is in the standard library
                if package_name == "asyncio":
                    print(f"{package_name} - installed (standard library)")
                else:
                    print(f"{package_name} - installed but unable to determine the version")
                
        except ImportError:
            print(f"{package_name} - not installed")
            missing_packages.append(package_name)
            all_packages_installed = False
    
   
    print("\n=== Summary ===")
    if all_packages_installed:
        print("Every depedencies are correctly installed.")
    else:
        print("Some dependencies are not installed or obsolete.")
        
        if missing_packages:
            print("\nMissing packages :")
            for pkg in missing_packages:
                print(f"  - {pkg}")
            print("\nInstal them with pip install " + " ".join(missing_packages))
        
        if outdated_packages:
            print("\nPackages to update :")
            for pkg in outdated_packages:
                print(f"  - {pkg}")
            print("\n Update them with : pip install --upgrade [package_name]")
    
    return all_packages_installed

if __name__ == "__main__":
    check_dependencies()