"""Seleção explícita do emitente. CNPJ identifica o contexto local, não é uma senha."""
import tkinter as tk
from tkinter import ttk,messagebox
from core import document

class CompanySession:
 def login_page(self):
    self.header('Selecionar emitente','Escolha a empresa cadastrada ou informe o CNPJ. Confirme o emitente antes de entrar.')
    box=ttk.Frame(self.content,style='Card.TFrame',padding=16);box.pack(fill='x',pady=(0,12))
    ttk.Label(box,text='CNPJ do emitente',style='Section.TLabel').pack(anchor='w')
    row=ttk.Frame(box);row.pack(fill='x',pady=(8,4))
    value=tk.StringVar();summary=tk.StringVar();matches={}
    def find(*args):
        cnpj=document(value.get());matches.clear()
        for cid,co in self.companies:
            if document(co.get('CNPJCPF',''))==cnpj:matches[cid]=co
        summary.set(next(iter(matches.values()))['xNome'] if len(matches)==1 else 'Selecione uma empresa na lista ou digite o CNPJ completo.')
    def enter(event=None):
        find()
        if len(matches)!=1:
            messagebox.showerror('Confira o CNPJ','Empresa não encontrada ou CNPJ duplicado. Confira o cadastro.',parent=self);return
        cid=next(iter(matches));self.company_id=cid;self.reset_note();self.page='home';self.refresh_companies();self.render()
    ttk.Button(row,text='+ Cadastrar empresa',command=lambda:self.edit_record('company')).pack(side='right',padx=(8,0))
    enter_button=ttk.Button(row,text='Entrar nesta empresa',command=enter,style='Accent.TButton');enter_button.pack(side='right',padx=(8,0))
    entry=ttk.Entry(row,textvariable=value,width=26);entry.pack(side='left',fill='x',expand=True);entry.bind('<Return>',enter)
    ttk.Label(box,textvariable=summary,wraplength=700,style='Sub.TLabel').pack(anchor='w',pady=(6,0))
    value.trace_add('write',find);find()
    hint=ttk.Label(self.content,text='Selecione na lista para preencher o CNPJ e clique em Entrar. CNPJ identifica o contexto local; não é uma senha.',style='Sub.TLabel',wraplength=750)
    hint.pack(side='bottom',anchor='w',pady=(8,0))
    ttk.Label(self.content,text='Empresas cadastradas',style='Section.TLabel').pack(anchor='w',pady=(0,8))
    frame=ttk.Frame(self.content);frame.pack(fill='both',expand=True)
    tree=ttk.Treeview(frame,columns=('CNPJ','name'),show='headings',height=5,selectmode='browse')
    tree.heading('CNPJ',text='CNPJ',anchor='w');tree.column('CNPJ',width=190,minwidth=170,stretch=False,anchor='w')
    tree.heading('name',text='Razão social',anchor='w');tree.column('name',width=400,minwidth=240,stretch=True,anchor='w')
    scroll=ttk.Scrollbar(frame,command=tree.yview);scroll.pack(side='right',fill='y');tree.configure(yscrollcommand=scroll.set);tree.pack(fill='both',expand=True)
    self.login_company_tree=tree
    for cid,co in sorted(self.companies,key=lambda pair:pair[1].get('xNome','').casefold()):
        tree.insert('','end',iid=cid,values=(co['CNPJCPF'],co['xNome']))
    def select(event=None):
        selected=tree.selection()
        if selected:value.set(next(co['CNPJCPF'] for cid,co in self.companies if cid==selected[0]))
    tree.bind('<<TreeviewSelect>>',select)
    tree.bind('<Double-1>',lambda e:enter_button.focus_set())
    entry.focus_set()
 def logout_company(self):
    if self.fiscal_busy:messagebox.showinfo('Aguarde','Conclua a operação fiscal antes de sair da empresa.');return
    if self.dirty and not messagebox.askyesno('Sair da empresa','Há um rascunho não salvo. Deseja sair e descartar as alterações?'):return
    self._cert_cache.clear();self.company_id=None;self.reset_note();self.page='home';self.refresh_companies();self.render()
