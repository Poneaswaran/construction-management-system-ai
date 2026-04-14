from rag.chroma_client import collection
from services.llm import generate_answer, generate_client_answer

def ask(query, project_context=None):
    results = collection.query(
        query_texts=[query],
        n_results=3
    )

    context = "\n\n".join(results["documents"][0])

    if project_context:
        pc_str = (
            f"Project Name: {project_context.project_name}\n"
            f"Status: {project_context.status}\n"
            f"Budget: {project_context.budget}\n"
            f"Progress: {project_context.progress_percentage}%\n"
            f"Location: {project_context.location}\n"
            f"Date Range: {project_context.start_date} to {project_context.end_date}\n"
            f"Description: {project_context.description}\n"
            "- Milestones:\n"
        )
        for m in project_context.milestones:
            m_comp = f", Completed: {m.completed_at}" if m.completed_at else ""
            pc_str += f"  * [{m.status}] {m.title} (Due: {m.due_date}{m_comp})\n"
            
        context += f"\n\n--- PROJECT CONTEXT ---\n{pc_str}"

    return generate_answer(query, context)

def ask_client(message, all_projects=None, selected_project=None):
    results = collection.query(
        query_texts=[message],
        n_results=3
    )

    context = "\n\n".join(results["documents"][0])

    if selected_project:
        pc_str = (
            f"Project Name: {selected_project.project_name}\n"
            f"Status: {selected_project.status}\n"
            f"Budget: {selected_project.budget}\n"
            f"Progress: {selected_project.progress_percentage}%\n"
            f"Location: {selected_project.location}\n"
            f"Date Range: {selected_project.start_date} to {selected_project.end_date}\n"
            f"Description: {selected_project.description}\n"
            "- Milestones:\n"
        )
        for m in selected_project.milestones:
            m_comp = f", Completed: {m.completed_at}" if m.completed_at else ""
            pc_str += f"  * [{m.status}] {m.title} (Due: {m.due_date}{m_comp})\n"
            
        context += f"\n\n--- PROJECT CONTEXT ---\n{pc_str}"
        return generate_client_answer(message, context, mode="detail")
    
    elif all_projects:
        count = len(all_projects)
        pc_str = f"You have {count} active projects:\n"
        for i, p in enumerate(all_projects, 1):
            pc_str += f"{i}. {p.project_name} — Status: {p.status} ({p.progress_percentage}% complete)\n"
            
        context += f"\n\n--- PROJECT LIST ---\n{pc_str}"
        res = generate_client_answer(message, context, mode="list")
        # Ensure projects list is returned to the frontend
        if isinstance(res, dict) and "projects" in res:
            res["projects"] = all_projects
        return res

    return generate_client_answer(message, context, mode="list")