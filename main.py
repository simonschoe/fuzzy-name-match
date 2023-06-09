import re

import gradio as gr, pandas as pd
from thefuzz import fuzz, process
from tqdm import tqdm


app = gr.Blocks()


def normalize_company_names(x: str):
    '''Clean company names and prepare for fuzzy matching'''
    # lowercasing
    x = str(x).lower().strip()
    # remove special characters
    x = re.sub(r'[^a-z0-9 ]', '', x)
    # remover certain trailing artifacts
    x = re.sub(r' (q[1-4].*?|old|adr)$', '', x)  # SA / Compustat
    x = re.sub(r' (cl a|cl b|redh)$', '', x)  # ExecuComp
    # remove legal forms
    x = re.sub(
        r' (public limited company|public limited|limited|unlimited|partnership|incorporation|incorporated|corporation|plc|pbc|ltd|inc|corp|llc|lp)$',
        '', x)
    # normalize other frequent error cases
    x = re.sub(r' co$', ' company', x)
    x = re.sub(r'^the ', '', x)
    x = re.sub(r' and ', ' ', x)
    # remove of whitespaces
    x = x.replace(' ', '')
    return x


def normalize_person_names(x):
    '''Clean company names and prepare for fuzzy matching'''
    # remove special characters
    x = re.sub(r'[^A-Za-z0-9 ]', '', x)
    # remove title
    x = re.sub(
        r' (Economics|PharmD|CISA|MPPM|Hons|Hon|BBA|MBA|JD|MIM|PhD|Hon|FCPA|CFA|CPA|FCA|CMA|MAI|BSc|BSC|MSc|MSC|ESQ|MS|BA|CA|BE|AM|PE|AO|MD)',
        '', x)
    # lowercasing
    x = str(x).lower().strip()
    # sort names alphabetically
    x = x.split()
    x.sort()
    x = ''.join(x)
    return x


def fuzzy_match(query: pd.DataFrame, q_name_norm: str,
                db: pd.DataFrame, db_name_norm: str, db_name_id: str, db_name: str,
                q_fy: str = None, q_qtr: str = None, db_fy: str = None, db_qtr: str = None):
    '''Fuzzy match nearest neighbours for query in (filtered) database based on Levenshtein Distance

    :param pd.DataFrame query:
        DataFrame from which to query
    :param str q_name_norm:
        Column name of normalized string column in query

    :param pd.DataFrame db:
        DataFrame in which to search for match
    :param str db_name_norm:
        Column name of normalized string column in database
    :param str db_name_id:
        Column name of id column in database
    :param str db_name:
        Column name of string column in database

    :param str q_fy:
        Column name of fiscal year column in query (for filtering)
    :param str q_qtr:
        Column name of fiscal quarter column in query (for filtering)
    :param str db_fy:
        Column name of fiscal year column in database (for filtering)
    :param str db_qtr:
        Column name of fiscal quarter column in database (for filtering)

    :return pd.Series neihbours:
        Series of tuples of the form (nearest neighbour:str, similarity score:int, gvkey:int)

    '''

    def retrieve_nn(x: pd.DataFrame, db: pd.DataFrame):
        ''' Fuzzy match nearest neighbour for query string '''

        # limit fuzzy match to relevant time interval
        if q_fy and q_qtr and db_fy and db_qtr:
            db = db[(db[db_fy] == x[q_fy]) & (db[db_qtr] == x[q_qtr])]
        elif q_fy and db_fy:
            db = db[(db[db_fy] == x[q_fy])]

        # retrieve nearest neighbour
        try:
            nn, score, _ = process.extractOne(x[q_name_norm], db[db_name_norm], scorer=fuzz.ratio)
            id = db[db[db_name_norm]==nn][db_name_id]
            id = id.item() if len(id)==1 else ', '.join(str(x) for x in id.tolist())
            name = db[db[db_name_norm]==nn][db_name]
            name = name.item() if len(name)==1 else ', '.join(str(x) for x in name.tolist())
            return (nn, score, id, name)
        except:
            return (None, None, None, None)

    tqdm.pandas()
    return query.progress_apply(lambda x: retrieve_nn(x, db), axis=1)


def perform(m_file, m_id, m_name, m_year, m_qtr, u_file, u_id, u_name, u_year, u_qtr, normalize_person=False, out='out', progress=gr.Progress(track_tqdm=True)):
    m_file = m_file.name
    # m_file_extension = m_file[m_file.rfind('.'):]
    u_file = u_file.name
    # u_file_extension = u_file[u_file.rfind('.'):]
    if m_file[-4:] == '.csv':
        master = pd.read_csv(m_file)
    elif m_file[-4:] == '.dta':
        master = pd.read_stata(m_file)
    else:
        raise ValueError("Please input either .csv or .dta")
    if u_file[-4:] == '.csv':
        using = pd.read_csv(u_file)
    elif u_file[-4:] == '.dta':
        using = pd.read_stata(u_file)
    else:
        raise ValueError("Please input either .csv or .dta")

    m_name_norm = f'{m_name}_norm'
    u_name_norm = f'{u_name}_norm'

    normalize_func = normalize_person_names if normalize_person=="Person names" else normalize_company_names
    print(normalize_person)
    master = master.assign(**{m_name_norm: master[m_name].map(lambda x: normalize_func(x))})
    using = using.assign(**{u_name_norm: using[u_name].map(lambda x: normalize_func(x))})

    master['nn_match'], master['nn_score'], master[f'nn_{u_id}'], master[f'nn_{u_name}'] = \
        zip(*fuzzy_match(master, m_name_norm,
                         using, u_name_norm, u_id, u_name,
                         q_fy=m_year, q_qtr=m_qtr, db_fy=u_year, db_qtr=u_qtr))

    if m_file[-4:] == '.csv':
        out_path = 'output.csv'
        master.to_csv(out_path, sep=';')
    else:
        out_path = 'output.dta'
        master.to_stata(out_path, version=118)

    return out_path


with app:
    gr.Markdown("# Fuzzy Name Match")
    with gr.Row():
        # input column 1
        with gr.Column():
            M_FILE = gr.File(label="Master file")
            M_ID = gr.Textbox(lines=1, value="secid", label="ID")
            M_NAME = gr.Textbox(lines=1, value="cname", label="Name")
            M_YEAR = gr.Textbox(lines=1, value="", label="Year")
            M_QTR = gr.Textbox(lines=1, value="", label="Qtr")
        # input column 2
        with gr.Column():
            U_FILE = gr.File(label="Using file")
            U_ID = gr.Textbox(lines=1, value="gvkey", label="ID")
            U_NAME = gr.Textbox(lines=1, value="coname", label="Name")
            U_YEAR = gr.Textbox(lines=1, value="", label="Year")
            U_QTR = gr.Textbox(lines=1, value="", label="Qtr")
        with gr.Column():
            with gr.Accordion("Open to see manual!", open=False):
                gr.Markdown("Lorem ipsum dolor sit amet, consetetur sadipscing elitr")
            normalize_which = gr.Radio(label="Normalize", choices=["Company names", "Person names"], value="Company names")
            compute_bt = gr.Button("Compute")
            f_out = gr.File(interactive=False, label="Download")
        compute_bt.click(perform, inputs=[M_FILE, M_ID, M_NAME, M_YEAR, M_QTR, U_FILE, U_ID, U_NAME, U_YEAR, U_QTR, normalize_which], outputs=[f_out])


app.queue().launch(server_name='0.0.0.0')

