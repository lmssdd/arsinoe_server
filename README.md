# arsinoe_webserver

**arsinoe_webserver** is a FastAPI-based backend service developed within the European project **ARSINOE – Climate Resilient-regions through Systemic Solutions and Innovations** (Horizon 2020, Grant Agreement No. 101037424).  

The service integrates meteorological, climatological, and remote-sensing data to support crop growth and water-management analyses (e.g., AquaCrop-based simulations) in Mediterranean environments. It is designed as a modular and extensible platform, enabling reproducible experiments and integration with digital twin approaches for agricultural water management.

---

## ARSINOE Project

- **Full title**: Climate Resilient-regions through Systemic Solutions and Innovations  
- **Programme**: Horizon 2020 – Research and Innovation Programme  
- **Grant Agreement**: No. 101037424  
- **Duration**: 48 months  
- **Budget**: ~15 million EUR  
- **Consortium**: 41 partners across Europe  
- **Coordinator**: University of Thessaly (Greece)  
- **Demonstrators**: 9 case studies, including the Mediterranean region (e.g., Sardinia)  

ARSINOE aims to create climate-resilient regions through systemic solutions and innovations. The project combines the **Systems Innovation Approach (SIA)** and the **Climate Innovation Window (CIW)** to establish an ecosystem for climate adaptation.  

In addition to this backend service, ARSINOE is developing a portfolio of digital tools such as a **Dashboard, Digital Twin frameworks, Knowledge Graphs, Data Hubs, Risk Assessment Tools**, and participatory platforms for stakeholder engagement across Europe.  

More information: 🌍 [ARSINOE official website](https://arsinoe-project.eu) | 📄 [CORDIS project page](https://cordis.europa.eu/project/id/101037424)

---

## Preprint

Methodology and case studies are described in the following preprint:

**Assessing the Impact of Supplemental Irrigation on Durum Wheat Production in a Drought-Prone Mediterranean Environment**  
Marino Marrocu, Marco Dettori, Luca Massidda, Giulia Urracci, Gabriella Pusceddu, Valentina Mereu, Simone Manca, Gianluca Dettori  
*SSRN Preprint, ID 5247560*  

🔗 [Read the preprint on SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5247560)

### BibTeX citation

```bibtex
@article{marrocu5247560assessing,
  title={Assessing the Impact of Supplemental Irrigation on Durum Wheat Production in a Drought-Prone Mediterranean Environment},
  author={Marrocu, Marino and Dettori, Marco and Massidda, Luca and Urracci, Giulia and Pusceddu, Gabriella and Mereu, Valentina and Manca, Simone and Dettori, Gianluca},
  journal={Available at SSRN 5247560}
}
```

## Quick start
```
# clone repository
git clone https://github.com/lmssdd/arsinoe_server.git
cd arsinoe_server

# install dependencies (Python >= 3.10 recommended)
pip install -r requirements.txt

# run development server
uvicorn main:app --reload

# production example (Gunicorn + Uvicorn worker)
gunicorn -k uvicorn.workers.UvicornWorker -c gunicorn.conf.py main:app
```

## Acknowledgements
This work was carried out within the framework of the ARSINOE project, funded by the European Union’s Horizon 2020 Research and Innovation Programme under Grant Agreement No. 101037424.
The authors gratefully acknowledge the contributions of all project partners and the support of the European Commission.

## License
This repository is released under the MIT License.