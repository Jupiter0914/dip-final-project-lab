function pso_worker(root, spool)
% Unmodified File Exchange solver. One process serves all seeded developer trials.
addpath(fullfile(root,'data','poly02','upf'));
if isempty(which('poly2mask')), error('Image Processing Toolbox unavailable'); end
fid=fopen(fullfile(spool,'ready.part'),'w');
fprintf(fid,'%s\n%s\n',version,which('getPSO_EA_Coords')); fclose(fid);
movefile(fullfile(spool,'ready.part'),fullfile(spool,'ready.txt'));
idx=1;
while true
    request=fullfile(spool,sprintf('in_%03d.mat',idx));
    while ~isfile(request)
        if isfile(fullfile(spool,'stop')), return; end
        pause(0.005);
    end
    job=load(request);
    p=[]; author_iou=NaN; dice=NaN; message='';
    t=tic;
    try
        A=logical(job.mask);
        stats=regionprops(A,'Centroid','Area');
        assert(isscalar(stats),'Standardized input must have one component');
        rng(double(job.seed),'twister');
        sol=getPSO_EA_Coords(A,stats.Centroid,double(job.k),stats.Area,1,0,0);
        p=sol.p; author_iou=sol.IoU; dice=sol.DICE;
    catch err
        message=getReport(err,'extended','hyperlinks','off');
    end
    solver_s=toc(t);
    dest=fullfile(spool,sprintf('out_%03d.mat',idx));
    save([dest '.tmp.mat'],'p','author_iou','dice','solver_s','message');
    movefile([dest '.tmp.mat'],dest);
    idx=idx+1;
end
end
